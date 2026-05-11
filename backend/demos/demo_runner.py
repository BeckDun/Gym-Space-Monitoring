"""
Demo runner — yields step-by-step log entries for each SAD use case.

Each run_* function is an async generator that yields dicts:
  {
    "step": str,      # SAD component name
    "arrow": str,     # source → destination
    "msg":  str,      # detail
    "type": str,      # "info" | "result" | "alert" | "db" | "done" | "error"
  }

All demo components share a single DatabaseController and SystemController
so the DB state is visible in real time via /api/demos/db-state.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import AsyncIterator

logger = logging.getLogger(__name__)

# ── Shared component instances ───────────────────────────────────────────────

_db = None
_device_driver = None
_system_controller = None

# Injected from main.py so demos share the live WebSocket-connected components
_shared_db = None
_shared_device_driver = None
_shared_system_controller = None


def set_shared_components(db, device_driver, system_controller) -> None:
    """Called from main.py after startup — lets demos push alerts to real WebSocket clients."""
    global _shared_db, _shared_device_driver, _shared_system_controller
    _shared_db = db
    _shared_device_driver = device_driver
    _shared_system_controller = system_controller


def _get_components():
    """Return the shared main-app components if available, else create a standalone set."""
    global _db, _device_driver, _system_controller
    if _shared_db is not None:
        return _shared_db, _shared_device_driver, _shared_system_controller

    from backend.db.database_controller import DatabaseController
    from backend.sensor.device_driver import DeviceDriver
    from backend.controller.system_controller import SystemController

    _db = DatabaseController()
    _db.init_db()
    _db.seed_members()
    _device_driver = DeviceDriver()
    _system_controller = SystemController(device_driver=_device_driver, database_controller=_db)
    return _db, _device_driver, _system_controller


def _entry(step: str, arrow: str, msg: str, type_: str = "info") -> dict:
    return {"step": step, "arrow": arrow, "msg": msg, "type": type_, "ts": datetime.utcnow().isoformat()}


# ── Asset video paths ────────────────────────────────────────────────────────

FALL_VIDEOS = {
    "fall_obvious":       "assets/fall_obvious.mp4",
    "fall_trip_recovery": "assets/fall_trip_recovery.mp4",
}
CONFLICT_VIDEOS = {
    "conflict_fight": "assets/conflict_fight.mp4",
    "conflict_push":  "assets/conflict_push.mp4",
}

# Per-clip mock MLLM outputs — each clip has its own expected classification
# so the demo shows both TRUE POSITIVE and TRUE NEGATIVE cases.
MOCK_OUTPUTS: dict[str, str] = {
    "assets/fall_obvious.mp4":       "Fall: 9, Confidence: 9",   # obvious fall → ALERT
    "assets/fall_trip_recovery.mp4": "Fall: 2, Confidence: 8",   # trip + recovery → no alert
    "assets/conflict_fight.mp4":     "Conflict: 8, Confidence: 9", # real altercation → ALERT
    "assets/conflict_push.mp4":      "Conflict: 2, Confidence: 7", # minor push → no alert
}

# Fallback defaults (legacy / used when no video is specified)
MOCK_FALL_OUTPUT     = MOCK_OUTPUTS["assets/fall_obvious.mp4"]
MOCK_CONFLICT_OUTPUT = MOCK_OUTPUTS["assets/conflict_fight.mp4"]


def _use_mock() -> bool:
    from backend.config import USE_MOCK_MLLM
    return USE_MOCK_MLLM


# ── 1. Fall Detection ────────────────────────────────────────────────────────

async def run_fall_detection(video_path: str | None = None) -> AsyncIterator[dict]:
    db, dd, ctrl = _get_components()
    video_path = video_path or FALL_VIDEOS["fall_obvious"]
    zone_id    = "cardio_zone"
    mock       = _use_mock()

    # Label shown in the log — strip folder prefix for readability
    clip_label = os.path.basename(video_path).replace("_", " ").replace(".mp4", "").title()

    from backend.sensor.sensor_driver import CameraDriver
    from backend.sensor.sensor_interface import SensorInterface
    from backend.processing.mllm_processor import MLLMProcessor
    from backend.processing.fall_detection import FALL_PROMPT, FallDetection

    yield _entry("CameraDriver", "CameraDriver → SensorInterface",
                 f"Reading clip: '{clip_label}' ({video_path})")
    await asyncio.sleep(0.3)

    camera_driver = CameraDriver(video_path=video_path, zone_id=zone_id)
    raw = camera_driver.read()
    size_kb = len(raw.data) / 1024

    yield _entry("SensorInterface", "SensorInterface → MLLMProcessor",
                 f"normalize_signal(RawSignal) → Event(type='video', zone='{zone_id}', size={size_kb:.0f} KB)")
    await asyncio.sleep(0.3)

    sensor_interface = SensorInterface()
    event = sensor_interface.normalize_signal(raw)

    if mock:
        mock_out = MOCK_OUTPUTS.get(video_path, MOCK_FALL_OUTPUT)
        yield _entry("MLLMProcessor", "MLLMProcessor → FallDetection",
                     f"[MOCK] Simulated MLLM response for '{clip_label}': \"{mock_out}\"", "result")
        mllm_output = mock_out
    else:
        yield _entry("MLLMProcessor", "MLLMProcessor → Gemini API",
                     f"analyze(event, FALL_PROMPT) — sending {size_kb:.0f} KB to Gemini...")
        await asyncio.sleep(0.2)
        mllm_processor = MLLMProcessor()
        loop = asyncio.get_event_loop()
        mllm_output = await loop.run_in_executor(None, mllm_processor.analyze, event, FALL_PROMPT)
        yield _entry("MLLMProcessor", "Gemini API → FallDetection",
                     f"Gemini response: \"{mllm_output}\"", "result")

    await asyncio.sleep(0.3)

    fall_detection = FallDetection(system_controller=ctrl)
    yield _entry("FallDetection", "FallDetection → SystemController",
                 f"analyze_mllm_output(\"{mllm_output}\", zone='{zone_id}')")
    await asyncio.sleep(0.3)

    before_count = len(ctrl.active_alerts)
    fall_detection.analyze_mllm_output(mllm_output, zone_id)
    new_alerts = ctrl.active_alerts[before_count:]

    if new_alerts:
        a = new_alerts[-1]
        yield _entry("SystemController", "SystemController → DeviceDriver",
                     f"receive_alert_trigger → dispatch_alert(Alert[{a.severity}])", "alert")
        await asyncio.sleep(0.3)
        yield _entry("DeviceDriver", "DeviceDriver → Staff Tablet",
                     f"push_to_tablet: [{a.severity}] {a.description[:100]}", "alert")
        await asyncio.sleep(0.3)
        db.log_alerts(a)
        yield _entry("DatabaseController", "DatabaseController → Data Store",
                     f"log_alerts(Alert) — severity={a.severity}, zone={a.zone_id}", "db")
    else:
        yield _entry("FallDetection", "FallDetection",
                     f"'{clip_label}' — fall score below threshold. Correctly classified: no alert.", "result")

    yield _entry("DONE", "", "", "done")


# ── 2. Abnormal Heart Rate ────────────────────────────────────────────────────

async def run_heart_rate() -> AsyncIterator[dict]:
    """
    Realistic biometric simulation:
      Phase 1 — Member checks in at entrance (real GymSession)
      Phase 2 — Member enters smart_machine_zone (wristband zone signal)
      Phase 3 — Member starts & completes a bench press set (EquipmentDriver)
      Phase 4 — Wristband reports abnormal HR spike post-workout
      Phase 5 — BiometricAnalysis triggers WARNING → Staff Tablet + Wristband
    """
    db, dd, ctrl = _get_components()
    ZONE = "smart_machine_zone"

    from backend.sensor.sensor_driver import WristbandDriver, EquipmentDriver
    from backend.sensor.sensor_interface import SensorInterface
    from backend.processing.biometric_analysis import BiometricAnalysis, HealthProfile
    from backend.db.database_controller import BiometricData, OccupancyData, EquipmentData
    from backend.db.models import Member as MemberModel

    sensor_interface = SensorInterface()

    # ── Phase 1: Find / tap in a member ──────────────────────────────────────
    all_members = db.get_members_with_status()
    if not all_members:
        yield _entry("Error", "", "No members in DB. Add members first.", "error")
        yield _entry("DONE", "", "", "done")
        return

    # Prefer a member already in gym; otherwise tap one in
    candidate = next((m for m in all_members if m["in_gym"]), None) or all_members[0]

    if not candidate["in_gym"]:
        yield _entry("EntranceDriver", "EntranceDriver → SensorInterface",
                     f"NFC tap — {candidate['name']} ({candidate['id']}) entering gym")
        await asyncio.sleep(0.6)
        db.log_session(member_id=candidate["id"], action="entry")
        total_in = sum(1 for x in db.get_members_with_status() if x["in_gym"])
        dd.broadcast_to_tablets({"type": "member_update", "in_gym_count": total_in})
        yield _entry("DatabaseController", "SensorInterface → DatabaseController",
                     f"log_session('{candidate['id']}', 'entry') — {total_in} member(s) now in gym",
                     "result")
        await asyncio.sleep(0.7)
    else:
        yield _entry("EntranceDriver", "System",
                     f"{candidate['name']} ({candidate['id']}) already checked in")
        await asyncio.sleep(0.4)

    mid  = candidate["id"]
    name = candidate["name"]

    # Read full profile (including bmi) directly from DB model
    with db._session() as session:
        row = session.query(MemberModel).filter_by(id=mid).first()
        bmi          = float(row.bmi)
        activity     = row.activity_level
        hr_low       = float(row.heart_rate_threshold_low)
        hr_high      = float(row.heart_rate_threshold_high)
        age          = int(row.age)

    profile = HealthProfile(
        member_id=mid, age=age, bmi=bmi, activity_level=activity,
        heart_rate_threshold_low=hr_low, heart_rate_threshold_high=hr_high,
    )

    yield _entry("DatabaseController", "DatabaseController → BiometricAnalysis",
                 f"Loaded health profile for {name} — age: {age}, activity: {activity}, "
                 f"HR thresholds: {hr_low}–{hr_high} bpm")
    await asyncio.sleep(0.7)

    # ── Phase 2: Member walks to smart_machine_zone ───────────────────────────
    resting_hr = round(hr_low + (hr_high - hr_low) * 0.25, 1)   # ~25% into range
    yield _entry("WristbandDriver", "WristbandDriver → SensorInterface",
                 f"{name}'s wristband: entering '{ZONE}' — resting HR: {resting_hr} bpm")
    await asyncio.sleep(0.5)

    wrist_driver = WristbandDriver(member_id=mid, zone_id=ZONE, heart_rate=resting_hr)
    event = sensor_interface.normalize_signal(wrist_driver.read())
    db.log_bio_occupancy(
        BiometricData(member_id=mid, heart_rate=resting_hr, spo2=99.0, zone_id=ZONE),
        OccupancyData(zone_id=ZONE, count=1),
    )
    dd.broadcast_to_tablets({"type": "zone_update", "zones": {ZONE: 1}, "alert_states": {}})
    yield _entry("DatabaseController", "SensorInterface → DatabaseController",
                 f"log_bio_occupancy — {name} in '{ZONE}', HR: {resting_hr} bpm (normal)", "db")
    await asyncio.sleep(0.7)

    # ── Phase 3: Member uses bench press ─────────────────────────────────────
    machine_id    = "bench_press_01"
    machine_label = "Bench Press"
    reps, resistance = 10, 70.0
    workout_hr = round(hr_low + (hr_high - hr_low) * 0.65, 1)   # ~65% into range — elevated but fine

    yield _entry("EquipmentDriver", "EquipmentDriver → SensorInterface",
                 f"{name} taps NFC on {machine_label} ({machine_id}) — session starting")
    await asyncio.sleep(0.6)

    eq_driver = EquipmentDriver(
        machine_id=machine_id, zone_id=ZONE,
        member_id=mid, reps=reps, resistance=resistance,
    )
    eq_event = sensor_interface.normalize_signal(eq_driver.read())
    eq_data = EquipmentData(
        member_id=eq_event.member_id,
        machine_id=eq_event.payload["machine_id"],
        zone_id=eq_event.zone_id,
        reps=eq_event.payload["reps"],
        resistance=eq_event.payload["resistance"],
    )
    db.log_weight_lifting(eq_data)
    yield _entry("SensorInterface", "SensorInterface → DatabaseController",
                 f"normalize_signal → Event(type='equipment', member='{name}', "
                 f"reps={reps}, resistance={resistance} lbs)")
    await asyncio.sleep(0.5)

    yield _entry("DatabaseController", "DatabaseController → Data Store",
                 f"log_weight_lifting — {name}: {reps} reps @ {resistance} lbs on {machine_label}", "db")
    await asyncio.sleep(0.8)

    # Mid-set HR reading (elevated but within range)
    db.log_bio_occupancy(
        BiometricData(member_id=mid, heart_rate=workout_hr, spo2=98.0, zone_id=ZONE),
        OccupancyData(zone_id=ZONE, count=1),
    )
    yield _entry("WristbandDriver", "WristbandDriver → SensorInterface",
                 f"{name}'s HR mid-set: {workout_hr} bpm — within thresholds ({hr_low}–{hr_high})")
    await asyncio.sleep(0.7)

    yield _entry("EquipmentDriver", f"{machine_label}",
                 f"{name} completes set — {reps} reps @ {resistance} lbs. Taps out of machine.")
    await asyncio.sleep(0.8)

    # ── Phase 4: Post-workout HR spike ────────────────────────────────────────
    abnormal_hr = round(hr_high + 35.0, 1)   # clearly above the member's personal threshold

    yield _entry("WristbandDriver", "WristbandDriver → SensorInterface",
                 f"{name}'s wristband: post-workout HR spike detected — {abnormal_hr} bpm "
                 f"(threshold: {hr_high} bpm)")
    await asyncio.sleep(0.6)

    spike_driver = WristbandDriver(member_id=mid, zone_id=ZONE, heart_rate=abnormal_hr)
    spike_event  = sensor_interface.normalize_signal(spike_driver.read())

    yield _entry("SensorInterface", "SensorInterface → BiometricAnalysis",
                 f"normalize_signal → Event(type='biometric', HR={abnormal_hr})")
    await asyncio.sleep(0.5)

    # ── Phase 5: BiometricAnalysis evaluates and triggers alert ───────────────
    yield _entry("BiometricAnalysis", "BiometricAnalysis — evaluateHeartRate()",
                 f"HR {abnormal_hr} bpm vs {name}'s thresholds [{hr_low}–{hr_high}] bpm — "
                 f"EXCEEDS upper threshold by {round(abnormal_hr - hr_high, 1)} bpm")
    await asyncio.sleep(0.6)

    before_count = len(ctrl.active_alerts)
    bio_analysis = BiometricAnalysis(system_controller=ctrl)
    bio_analysis.process_event(spike_event, profile)

    db.log_bio_occupancy(
        BiometricData(member_id=mid, heart_rate=abnormal_hr, spo2=96.0, zone_id=ZONE),
        OccupancyData(zone_id=ZONE, count=1),
    )
    yield _entry("DatabaseController", "DatabaseController → Data Store",
                 f"log_bio_occupancy — {name}: HR={abnormal_hr} bpm (abnormal), SpO2=96%", "db")
    await asyncio.sleep(0.5)

    new_alerts = ctrl.active_alerts[before_count:]
    if new_alerts:
        a = new_alerts[-1]
        yield _entry("SystemController", "SystemController → DeviceDriver",
                     f"dispatch_alert(Alert[{a.severity}]) — to Staff Tablet AND {name}'s wristband",
                     "alert")
        await asyncio.sleep(0.4)
        yield _entry("DeviceDriver", "DeviceDriver → Staff Tablet + Wristband",
                     f"push_to_tablet([{a.severity}] {a.description[:80]}) "
                     f"+ push_to_wristband('{mid}', 'Reduce intensity')",
                     "alert")
        db.log_alerts(a)
        yield _entry("DatabaseController", "DatabaseController → Data Store",
                     f"log_alerts(Alert[{a.severity}]) — member: {name}, zone: {ZONE}", "db")
    else:
        yield _entry("BiometricAnalysis", "",
                     f"HR {abnormal_hr} bpm did not trigger threshold — check thresholds.", "info")

    yield _entry("DONE", "", "", "done")


# ── 3. Overcrowding Detection ─────────────────────────────────────────────────

async def run_overcrowding() -> AsyncIterator[dict]:
    """
    Full gym simulation:
      Phase 1 — Announce & read current state
      Phase 2 — Tap in enough members to fill cardio_zone (real GymSession records)
      Phase 3 — All 10 members enter cardio_zone one by one (1 s apart)
      Phase 4 — Alert fires at cap (5), count continues to 10
      Phase 5 — Final overcrowding state logged to DB
    """
    db, dd, ctrl = _get_components()
    CARDIO  = "cardio_zone"
    CAP     = 5    # matches ZONE_THRESHOLDS and staff tablet ZONE_CAPS
    TARGET  = 10   # demo goal: double capacity in one zone

    from backend.sensor.sensor_driver import WristbandDriver
    from backend.sensor.sensor_interface import SensorInterface
    from backend.db.database_controller import BiometricData, OccupancyData
    from backend.processing.occupancy_manager import OccupancyManager

    occ = OccupancyManager(system_controller=ctrl)
    sensor_interface = SensorInterface()
    alert_logged = False   # log only the first overcrowding alert to DB

    def _push_zones():
        dd.broadcast_to_tablets({
            "type": "zone_update",
            "zones": dict(occ.zone_occupancy_counts),
            "alert_states": {
                z: ("overcrowded" if c >= CAP else "near-capacity" if c >= int(CAP * 0.8) else "")
                for z, c in occ.zone_occupancy_counts.items()
            },
        })

    def _enter_cardio(member, hr=85.0):
        driver = WristbandDriver(member_id=member["id"], zone_id=CARDIO, heart_rate=hr)
        event  = sensor_interface.normalize_signal(driver.read())
        occ.update_location_density(event.member_id, CARDIO)
        count  = occ.zone_occupancy_counts.get(CARDIO, 0)
        db.log_bio_occupancy(
            BiometricData(member_id=member["id"], heart_rate=hr, spo2=98.0, zone_id=CARDIO),
            OccupancyData(zone_id=CARDIO, count=count),
        )
        _push_zones()
        return count

    # ── Phase 1: Announce ─────────────────────────────────────────────────────
    yield _entry("System", "Demo → Gym Simulation",
                 f"Overcrowding simulation — zone capacity: {CAP} | target: {TARGET} members in '{CARDIO}'")
    await asyncio.sleep(1.0)

    all_members = db.get_members_with_status()
    if not all_members:
        yield _entry("Error", "", "No members in DB. Add members first.", "error")
        yield _entry("DONE", "", "", "done")
        return

    in_gym  = [m for m in all_members if     m["in_gym"]]
    outside = [m for m in all_members if not m["in_gym"]]

    yield _entry("DatabaseController", "DatabaseController → System",
                 f"Member status — in gym: {len(in_gym)}, outside: {len(outside)}, target: {TARGET}")
    await asyncio.sleep(0.8)

    # ── Phase 2: Ensure exactly TARGET members are available ──────────────────
    # Tap in anyone not yet in gym
    if in_gym:
        yield _entry("EntranceDriver", "System",
                     f"Already checked in: {', '.join(m['name'] for m in in_gym)}")
        await asyncio.sleep(0.5)

    for m in outside:
        yield _entry("EntranceDriver", "EntranceDriver → SensorInterface",
                     f"NFC tap — {m['name']} ({m['id']}) entering gym")
        await asyncio.sleep(0.6)
        db.log_session(member_id=m["id"], action="entry")
        total_in = sum(1 for x in db.get_members_with_status() if x["in_gym"])
        dd.broadcast_to_tablets({"type": "member_update", "in_gym_count": total_in})
        yield _entry("DatabaseController", "SensorInterface → DatabaseController",
                     f"log_session('{m['id']}', 'entry') — {total_in} members now in gym", "result")
        await asyncio.sleep(0.8)

    # Add extra members (via db.add_member) until we have TARGET available
    all_members = db.get_members_with_status()
    in_gym = [m for m in all_members if m["in_gym"]]
    extra_needed = max(0, TARGET - len(in_gym))

    if extra_needed:
        yield _entry("System", "DatabaseController → System",
                     f"Need {extra_needed} more member(s) to reach target of {TARGET} — registering now...")
        await asyncio.sleep(0.6)
        for i in range(extra_needed):
            new_m = db.add_member()
            db.log_session(member_id=new_m["id"], action="entry")
            total_in = sum(1 for x in db.get_members_with_status() if x["in_gym"])
            dd.broadcast_to_tablets({"type": "member_update", "in_gym_count": total_in})
            yield _entry("DatabaseController", "DatabaseController → EntranceDriver",
                         f"Registered & tapped in: {new_m['name']} ({new_m['id']}) — {total_in} in gym", "result")
            await asyncio.sleep(0.8)

    # Final member list (capped at TARGET)
    all_members = db.get_members_with_status()
    in_gym = [m for m in all_members if m["in_gym"]][:TARGET]

    # ── Phase 3: All TARGET members stream into cardio_zone ───────────────────
    yield _entry("OccupancyManager", "Entrance → Cardio Zone",
                 f"{len(in_gym)} members heading to '{CARDIO}' — capacity: {CAP}")
    await asyncio.sleep(1.0)

    for m in in_gym:
        cnt = _enter_cardio(m, hr=round(78.0 + cnt * 1.2, 1) if (cnt := occ.zone_occupancy_counts.get(CARDIO, 0)) else 78.0)
        pct = int(cnt / CAP * 100)

        if cnt < int(CAP * 0.8):
            status, etype = "", "info"
        elif cnt < CAP:
            status, etype = " ⚡ approaching capacity", "info"
        elif cnt == CAP:
            status, etype = f" ⚠ AT CAPACITY ({pct}%) — alert dispatched to staff tablet", "alert"
        else:
            status, etype = f" ⚠ OVERCROWDED  {cnt}/{CAP}  ({pct}% of capacity)", "alert"

        yield _entry(
            "WristbandDriver → OccupancyManager",
            "SensorInterface → OccupancyManager",
            f"{m['name']} → '{CARDIO}' — occupancy: {cnt}/{CAP}{status}",
            etype,
        )

        # Log the first overcrowding alert to DB once
        if cnt >= CAP and not alert_logged:
            new_alerts = [a for a in ctrl.active_alerts
                          if a.zone_id == CARDIO and not a.resolved]
            if new_alerts:
                db.log_alerts(new_alerts[-1])
                alert_logged = True

        await asyncio.sleep(1.0)   # ← slow: 1 second between each member

    # ── Phase 4: Final state summary ─────────────────────────────────────────
    final = occ.zone_occupancy_counts.get(CARDIO, 0)
    yield _entry("DatabaseController", "OccupancyManager → DatabaseController → Data Store",
                 f"Final occupancy logged — '{CARDIO}': {final} members present, capacity: {CAP} "
                 f"({int(final / CAP * 100)}% of max). Overcrowding alert active on Staff Tablet.",
                 "db")
    await asyncio.sleep(2.0)

    # ── Phase 5: Staff resolves alert → members disperse ─────────────────────
    yield _entry("Staff Tablet", "Staff Tablet → SystemController",
                 "Staff acknowledged alert — marking overcrowding alert as resolved...")
    await asyncio.sleep(1.5)

    # Grab the alert reference before resolving (resolve removes it from active list)
    cardio_alerts = [a for a in ctrl.active_alerts if a.zone_id == CARDIO and not a.resolved]
    if cardio_alerts:
        alert = cardio_alerts[0]
        resolved_payload = alert.to_dict()
        ctrl.resolve_alert(alert.alert_id)
        resolved_payload["resolved"] = True
        # Broadcast resolved state → staff tablet removes it from Active Alerts
        dd.broadcast_to_tablets(resolved_payload)
        yield _entry("SystemController", "SystemController → DeviceDriver → Staff Tablet",
                     f"Alert resolved — broadcast sent, removed from Active Alerts on Staff Tablet",
                     "result")
        await asyncio.sleep(1.0)

    # ── Phase 6: Members disperse to other zones ──────────────────────────────
    DISPERSE_ZONES = ["smart_machine_zone", "cycling_zone", "functional_zone"]
    yield _entry("OccupancyManager", "Staff → Members",
                 f"Staff directing {len(in_gym)} members to disperse from '{CARDIO}'...")
    await asyncio.sleep(1.0)

    for i, m in enumerate(in_gym):
        target = DISPERSE_ZONES[i % len(DISPERSE_ZONES)]
        driver = WristbandDriver(member_id=m["id"], zone_id=target, heart_rate=72.0)
        event  = sensor_interface.normalize_signal(driver.read())
        occ.update_location_density(event.member_id, target)
        cardio_cnt = occ.zone_occupancy_counts.get(CARDIO, 0)
        target_cnt = occ.zone_occupancy_counts.get(target, 0)
        db.log_bio_occupancy(
            BiometricData(member_id=m["id"], heart_rate=72.0, spo2=99.0, zone_id=target),
            OccupancyData(zone_id=target, count=target_cnt),
        )
        _push_zones()
        yield _entry("WristbandDriver → OccupancyManager", "SensorInterface → OccupancyManager",
                     f"{m['name']} dispersed → '{target}' — cardio now: {cardio_cnt}/{CAP}",
                     "info")
        await asyncio.sleep(1.0)

    yield _entry("System", "OccupancyManager → System",
                 f"'{CARDIO}' cleared — occupancy: {occ.zone_occupancy_counts.get(CARDIO, 0)}/{CAP}. "
                 f"Simulation complete.",
                 "result")

    yield _entry("DONE", "", "", "done")


# ── 4. Conflict Detection ─────────────────────────────────────────────────────

async def run_conflict_detection(video_path: str | None = None) -> AsyncIterator[dict]:
    db, dd, ctrl = _get_components()
    video_path  = video_path or CONFLICT_VIDEOS["conflict_fight"]
    zone_id     = "cardio_zone"
    mock        = _use_mock()
    clip_label  = os.path.basename(video_path).replace("_", " ").replace(".mp4", "").title()

    from backend.sensor.sensor_driver import CameraDriver
    from backend.sensor.sensor_interface import SensorInterface
    from backend.processing.conflict_detection import CONFLICT_PROMPT, ConflictDetection

    yield _entry("CameraDriver", "CameraDriver → SensorInterface",
                 f"Reading clip: '{clip_label}' ({video_path})")
    await asyncio.sleep(0.3)

    camera_driver = CameraDriver(video_path=video_path, zone_id=zone_id)
    raw = camera_driver.read()
    size_kb = len(raw.data) / 1024

    yield _entry("SensorInterface", "SensorInterface → MLLMProcessor",
                 f"normalize_signal → Event(type='video', zone='{zone_id}', size={size_kb:.0f} KB)")
    await asyncio.sleep(0.3)

    sensor_interface = SensorInterface()
    event = sensor_interface.normalize_signal(raw)

    if mock:
        mock_out = MOCK_OUTPUTS.get(video_path, MOCK_CONFLICT_OUTPUT)
        yield _entry("MLLMProcessor", "MLLMProcessor → ConflictDetection",
                     f"[MOCK] Simulated MLLM response for '{clip_label}': \"{mock_out}\"", "result")
        mllm_output = mock_out
    else:
        from backend.processing.mllm_processor import MLLMProcessor
        yield _entry("MLLMProcessor", "MLLMProcessor → Gemini API",
                     f"analyze(event, CONFLICT_PROMPT) — sending to Gemini...")
        await asyncio.sleep(0.2)
        mllm_processor = MLLMProcessor()
        loop = asyncio.get_event_loop()
        mllm_output = await loop.run_in_executor(None, mllm_processor.analyze, event, CONFLICT_PROMPT)
        yield _entry("MLLMProcessor", "Gemini API → ConflictDetection",
                     f"Gemini response: \"{mllm_output}\"", "result")

    await asyncio.sleep(0.3)

    conflict_detection = ConflictDetection(system_controller=ctrl)
    yield _entry("ConflictDetection", "ConflictDetection → SystemController",
                 f"analyze_mllm_output(\"{mllm_output}\", zone='{zone_id}')")
    await asyncio.sleep(0.3)

    before_count = len(ctrl.active_alerts)
    conflict_detection.analyze_mllm_output(mllm_output, zone_id)
    new_alerts = ctrl.active_alerts[before_count:]

    if new_alerts:
        a = new_alerts[-1]
        yield _entry("SystemController", "SystemController → DeviceDriver",
                     f"dispatch_alert(Alert[{a.severity}])", "alert")
        await asyncio.sleep(0.3)
        yield _entry("DeviceDriver", "DeviceDriver → Staff Tablet",
                     f"push_to_tablet: [{a.severity}] {a.description[:100]}", "alert")
        db.log_alerts(a)
        yield _entry("DatabaseController", "DatabaseController → Data Store",
                     f"log_alerts(Alert[{a.severity}]) — conflict in zone='{zone_id}'", "db")
    else:
        yield _entry("ConflictDetection", "ConflictDetection",
                     f"'{clip_label}' — conflict score below threshold. Correctly classified: no alert.", "result")

    yield _entry("DONE", "", "", "done")


# ── 5. Equipment Usage Reporting ──────────────────────────────────────────────

async def run_equipment_usage() -> AsyncIterator[dict]:
    """
    Equipment usage simulation:
      - Find (or tap in) a real member
      - Walk them through 3 machines in smart_machine_zone
      - Each machine: EquipmentDriver → SensorInterface → DatabaseController.log_weight_lifting()
      - Log all events with the member's real name; no report generated at end
    """
    db, dd, ctrl = _get_components()
    ZONE = "smart_machine_zone"

    from backend.sensor.sensor_driver import EquipmentDriver, WristbandDriver
    from backend.sensor.sensor_interface import SensorInterface
    from backend.db.database_controller import EquipmentData, BiometricData, OccupancyData

    sensor_interface = SensorInterface()

    # ── Find a tapped-in member (or tap one in) ───────────────────────────────
    all_members = db.get_members_with_status()
    in_gym = [m for m in all_members if m["in_gym"]]

    if not in_gym:
        # Tap in the first available member
        candidate = next((m for m in all_members if not m["in_gym"]), None)
        if not candidate:
            yield _entry("Error", "", "No members registered. Add members first.", "error")
            yield _entry("DONE", "", "", "done")
            return
        yield _entry("EntranceDriver", "EntranceDriver → SensorInterface",
                     f"No members checked in — tapping in {candidate['name']} ({candidate['id']})...")
        await asyncio.sleep(0.3)
        db.log_session(member_id=candidate["id"], action="entry")
        total_in = sum(1 for x in db.get_members_with_status() if x["in_gym"])
        dd.broadcast_to_tablets({"type": "member_update", "in_gym_count": total_in})
        yield _entry("DatabaseController", "SensorInterface → DatabaseController",
                     f"log_session('{candidate['id']}', 'entry') — {total_in} member(s) now in gym", "result")
        await asyncio.sleep(0.4)
        member = candidate
    else:
        member = in_gym[0]
        yield _entry("DatabaseController", "DatabaseController → System",
                     f"Using tapped-in member: {member['name']} ({member['id']})")
        await asyncio.sleep(0.3)

    mid  = member["id"]
    name = member["name"]

    # ── Member walks to smart_machine_zone ────────────────────────────────────
    yield _entry("WristbandDriver", "WristbandDriver → SensorInterface",
                 f"{name}'s wristband signal: entering '{ZONE}'")
    await asyncio.sleep(0.3)
    wrist_driver = WristbandDriver(member_id=mid, zone_id=ZONE, heart_rate=76.0)
    wrist_event  = sensor_interface.normalize_signal(wrist_driver.read())
    db.log_bio_occupancy(
        BiometricData(member_id=mid, heart_rate=76.0, spo2=99.0, zone_id=ZONE),
        OccupancyData(zone_id=ZONE, count=1),
    )
    dd.broadcast_to_tablets({
        "type": "zone_update",
        "zones": {ZONE: 1},
        "alert_states": {},
    })
    yield _entry("DatabaseController", "SensorInterface → DatabaseController",
                 f"log_bio_occupancy — {name} in '{ZONE}', HR: 76 bpm", "result")
    await asyncio.sleep(0.4)

    # ── Three machine sessions ────────────────────────────────────────────────
    machines = [
        ("bench_press_01",  "Bench Press",  12, 60.0,  82.0),
        ("cable_row_01",    "Cable Row",    15, 45.0,  78.0),
        ("leg_press_01",    "Leg Press",    10, 80.0,  88.0),
    ]

    for machine_id, machine_label, reps, resistance, hr in machines:
        yield _entry("EquipmentDriver", "EquipmentDriver → SensorInterface",
                     f"{name} sits at {machine_label} ({machine_id}) — NFC tap detected")
        await asyncio.sleep(0.35)

        driver = EquipmentDriver(
            machine_id=machine_id, zone_id=ZONE,
            member_id=mid, reps=reps, resistance=resistance,
        )
        raw   = driver.read()
        event = sensor_interface.normalize_signal(raw)

        yield _entry("SensorInterface", "SensorInterface → DatabaseController",
                     f"normalize_signal → Event(type='equipment', member='{name}', reps={reps}, resistance={resistance} lbs)")
        await asyncio.sleep(0.3)

        eq_data = EquipmentData(
            member_id=event.member_id,
            machine_id=event.payload["machine_id"],
            zone_id=event.zone_id,
            reps=event.payload["reps"],
            resistance=event.payload["resistance"],
        )
        db.log_weight_lifting(eq_data)

        # Update HR after set
        db.log_bio_occupancy(
            BiometricData(member_id=mid, heart_rate=hr, spo2=98.0, zone_id=ZONE),
            OccupancyData(zone_id=ZONE, count=1),
        )
        yield _entry("DatabaseController", "DatabaseController → Data Store",
                     f"log_weight_lifting — {name}: {reps} reps @ {resistance} lbs on {machine_label} | HR after set: {hr} bpm",
                     "db")
        await asyncio.sleep(0.4)

    # ── Session summary ───────────────────────────────────────────────────────
    yield _entry("DatabaseController", "DatabaseController → Data Store",
                 f"{name}'s session logged: {len(machines)} machines, "
                 f"{sum(m[2] for m in machines)} total reps across bench, cable row, leg press",
                 "result")

    yield _entry("DONE", "", "", "done")


# ── Router ────────────────────────────────────────────────────────────────────

DEMOS: dict[str, callable] = {
    "fall_detection": run_fall_detection,
    "heart_rate": run_heart_rate,
    "overcrowding": run_overcrowding,
    "conflict_detection": run_conflict_detection,
    "equipment_usage": run_equipment_usage,
}


async def run(demo_name: str, video_path: str | None = None) -> AsyncIterator[dict]:
    if demo_name not in DEMOS:
        yield _entry("Error", "", f"Unknown demo: '{demo_name}'. Valid: {list(DEMOS.keys())}", "error")
        return
    try:
        fn = DEMOS[demo_name]
        # Only MLLM demos accept video_path; others ignore extra kwargs
        import inspect
        kwargs = {"video_path": video_path} if "video_path" in inspect.signature(fn).parameters else {}
        async for entry in fn(**kwargs):
            yield entry
    except Exception as exc:
        logger.exception("Demo '%s' failed", demo_name)
        yield _entry("Error", "", f"Demo error: {exc}", "error")
        yield _entry("DONE", "", "", "done")


def get_db_state() -> dict:
    """Return current DB state for the demos page database viewer."""
    if _db is None:
        _get_components()
    return _db.get_full_state()
