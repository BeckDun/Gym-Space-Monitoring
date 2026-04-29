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

# ── Shared component instances (reset on each demo run) ─────────────────────

_db = None
_device_driver = None
_system_controller = None


def _init_components():
    global _db, _device_driver, _system_controller
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


# ── MOCK MLLM outputs (used when GEMINI_API_KEY is not set) ─────────────────

MOCK_FALL_OUTPUT = "Fall: 8, Confidence: 9"
MOCK_CONFLICT_OUTPUT = "Conflict: 7, Confidence: 8"


def _use_mock() -> bool:
    from backend.config import USE_MOCK_MLLM
    return USE_MOCK_MLLM


# ── 1. Fall Detection ────────────────────────────────────────────────────────

async def run_fall_detection() -> AsyncIterator[dict]:
    db, dd, ctrl = _init_components()
    video_path = "Man_Falling_in_Gym_Video.mp4"
    zone_id = "zone_a"
    mock = _use_mock()

    from backend.sensor.sensor_driver import CameraDriver
    from backend.sensor.sensor_interface import SensorInterface
    from backend.processing.mllm_processor import MLLMProcessor
    from backend.processing.fall_detection import FALL_PROMPT, FallDetection

    yield _entry("CameraDriver", "CameraDriver → SensorInterface",
                 f"Reading video file: {video_path}")
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
        yield _entry("MLLMProcessor", "MLLMProcessor → FallDetection",
                     f"[MOCK] No GEMINI_API_KEY — using mock output: \"{MOCK_FALL_OUTPUT}\"", "result")
        mllm_output = MOCK_FALL_OUTPUT
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

    fall_detection.analyze_mllm_output(mllm_output, zone_id)

    alerts = ctrl.get_active_alerts()
    if alerts:
        a = alerts[-1]
        yield _entry("SystemController", "SystemController → DeviceDriver",
                     f"receive_alert_trigger → dispatch_alert(Alert[{a['severity']}])", "alert")
        await asyncio.sleep(0.3)
        yield _entry("DeviceDriver", "DeviceDriver → Staff Tablet",
                     f"push_to_tablet: [{a['severity']}] {a['description'][:100]}", "alert")
        await asyncio.sleep(0.3)
        db.log_alerts(ctrl.active_alerts[-1])
        yield _entry("DatabaseController", "DatabaseController → Data Store",
                     f"log_alerts(Alert) — severity={a['severity']}, zone={a['zone_id']}", "db")
    else:
        yield _entry("FallDetection", "FallDetection",
                     "Fall score below threshold — no alert triggered.", "info")

    yield _entry("DONE", "", "", "done")


# ── 2. Abnormal Heart Rate ────────────────────────────────────────────────────

async def run_heart_rate() -> AsyncIterator[dict]:
    db, dd, ctrl = _init_components()
    zone_id = "zone_b"
    member_id = "member_002"  # Bob: threshold 50–140 bpm
    abnormal_hr = 175.0

    from backend.sensor.sensor_driver import WristbandDriver
    from backend.sensor.sensor_interface import SensorInterface
    from backend.processing.biometric_analysis import BiometricAnalysis, HealthProfile
    from backend.db.database_controller import BiometricData, OccupancyData

    yield _entry("WristbandDriver", "WristbandDriver → SensorInterface",
                 f"read() — member_id='{member_id}', heart_rate={abnormal_hr} bpm, zone='{zone_id}'")
    await asyncio.sleep(0.3)

    driver = WristbandDriver(member_id=member_id, zone_id=zone_id, heart_rate=abnormal_hr)
    raw = driver.read()

    yield _entry("SensorInterface", "SensorInterface → BiometricAnalysis",
                 f"normalize_signal(RawSignal) → Event(type='biometric', HR={abnormal_hr})")
    await asyncio.sleep(0.3)

    sensor_interface = SensorInterface()
    event = sensor_interface.normalize_signal(raw)

    profile = HealthProfile(
        member_id=member_id, age=45, bmi=27.8, activity_level="low",
        heart_rate_threshold_low=50.0, heart_rate_threshold_high=140.0,
    )
    yield _entry("BiometricAnalysis", "BiometricAnalysis — evaluateHeartRate()",
                 f"HR={abnormal_hr} vs thresholds [{profile.heart_rate_threshold_low}–{profile.heart_rate_threshold_high}] bpm")
    await asyncio.sleep(0.3)

    bio_analysis = BiometricAnalysis(system_controller=ctrl)
    bio_analysis.process_event(event, profile)

    bio_data = BiometricData(member_id=member_id, heart_rate=abnormal_hr, spo2=97.0, zone_id=zone_id)
    occ_data = OccupancyData(zone_id=zone_id, count=1)
    db.log_bio_occupancy(bio_data, occ_data)
    yield _entry("DatabaseController", "DatabaseController → Data Store",
                 f"log_bio_occupancy(BiometricData[HR={abnormal_hr}], OccupancyData[count=1])", "db")
    await asyncio.sleep(0.3)

    alerts = ctrl.get_active_alerts()
    if alerts:
        a = alerts[-1]
        yield _entry("SystemController", "SystemController → DeviceDriver",
                     f"dispatch_alert(Alert[{a['severity']}]) — to tablet AND wristband", "alert")
        await asyncio.sleep(0.3)
        yield _entry("DeviceDriver", "DeviceDriver → Staff Tablet + Wristband Screen",
                     f"push_to_tablet + push_to_wristband('{member_id}', warning)", "alert")
        db.log_alerts(ctrl.active_alerts[-1])
        yield _entry("DatabaseController", "DatabaseController → Data Store",
                     f"log_alerts(Alert[WARNING])", "db")
    else:
        yield _entry("BiometricAnalysis", "", "Heart rate within normal range — no alert.", "info")

    yield _entry("DONE", "", "", "done")


# ── 3. Overcrowding Detection ─────────────────────────────────────────────────

async def run_overcrowding() -> AsyncIterator[dict]:
    db, dd, ctrl = _init_components()
    zone_id = "zone_a"
    threshold = 5  # demo threshold — low so it triggers quickly
    num_members = 7

    from backend.sensor.sensor_driver import WristbandDriver
    from backend.sensor.sensor_interface import SensorInterface
    from backend.processing.occupancy_manager import OccupancyManager
    from backend.db.database_controller import BiometricData, OccupancyData

    # Override threshold for demo
    from unittest.mock import patch
    with patch("backend.processing.occupancy_manager.ZONE_THRESHOLDS", {zone_id: threshold, "zone_b": 10}):
        from backend.processing.occupancy_manager import OccupancyManager as OM
        occupancy_manager = OM(system_controller=ctrl)

    yield _entry("OccupancyManager", "", f"Zone '{zone_id}' capacity threshold: {threshold} patrons")
    await asyncio.sleep(0.3)

    sensor_interface = SensorInterface()

    for i in range(num_members):
        mid = f"demo_member_{i:02d}"
        driver = WristbandDriver(member_id=mid, zone_id=zone_id, heart_rate=80.0)
        raw = driver.read()
        event = sensor_interface.normalize_signal(raw)

        count_before = occupancy_manager.zone_occupancy_counts.get(zone_id, 0)
        occupancy_manager.update_location_density(event.member_id, zone_id)
        count_now = occupancy_manager.zone_occupancy_counts.get(zone_id, 0)

        status = ""
        if count_now >= threshold:
            status = " ⚠ OVERCROWDED"
        elif count_now >= int(threshold * 0.8):
            status = " ⚡ approaching capacity"

        yield _entry(
            "WristbandDriver → OccupancyManager",
            f"SensorInterface → OccupancyManager",
            f"Member {i+1}/{num_members} entered '{zone_id}' — count: {count_now}/{threshold}{status}",
            "alert" if status else "info",
        )
        await asyncio.sleep(0.25)

    occ_data = OccupancyData(zone_id=zone_id, count=occupancy_manager.zone_occupancy_counts.get(zone_id, 0))
    from backend.db.database_controller import BiometricData, OccupancyData
    db.log_bio_occupancy(
        BiometricData(member_id="member_001", heart_rate=78.0, spo2=98.0, zone_id=zone_id),
        occ_data,
    )
    yield _entry("DatabaseController", "DatabaseController → Data Store",
                 f"log_bio_occupancy — zone='{zone_id}', count={occ_data.count}", "db")
    await asyncio.sleep(0.3)

    alerts = ctrl.get_active_alerts()
    if alerts:
        for a in alerts:
            yield _entry("SystemController → DeviceDriver",
                         "SystemController → DeviceDriver → Staff Tablet",
                         f"[{a['severity']}] {a['description']}", "alert")
            db.log_alerts(ctrl.active_alerts[alerts.index(a)])
    yield _entry("DONE", "", "", "done")


# ── 4. Conflict Detection ─────────────────────────────────────────────────────

async def run_conflict_detection() -> AsyncIterator[dict]:
    db, dd, ctrl = _init_components()
    video_path = "Man_Falling_in_Gym_Video.mp4"
    zone_id = "zone_a"
    mock = _use_mock()

    from backend.sensor.sensor_driver import CameraDriver
    from backend.sensor.sensor_interface import SensorInterface
    from backend.processing.conflict_detection import CONFLICT_PROMPT, ConflictDetection

    yield _entry("CameraDriver", "CameraDriver → SensorInterface",
                 f"read() — video file: {video_path}")
    await asyncio.sleep(0.3)

    camera_driver = CameraDriver(video_path=video_path, zone_id=zone_id)
    raw = camera_driver.read()
    size_kb = len(raw.data) / 1024

    yield _entry("SensorInterface", "SensorInterface → MLLMProcessor",
                 f"normalize_signal → Event(type='video', size={size_kb:.0f} KB)")
    await asyncio.sleep(0.3)

    sensor_interface = SensorInterface()
    event = sensor_interface.normalize_signal(raw)

    if mock:
        yield _entry("MLLMProcessor", "MLLMProcessor → ConflictDetection",
                     f"[MOCK] No GEMINI_API_KEY — using mock output: \"{MOCK_CONFLICT_OUTPUT}\"", "result")
        mllm_output = MOCK_CONFLICT_OUTPUT
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

    conflict_detection.analyze_mllm_output(mllm_output, zone_id)

    alerts = ctrl.get_active_alerts()
    if alerts:
        a = alerts[-1]
        yield _entry("SystemController", "SystemController → DeviceDriver",
                     f"dispatch_alert(Alert[{a['severity']}])", "alert")
        await asyncio.sleep(0.3)
        yield _entry("DeviceDriver", "DeviceDriver → Staff Tablet",
                     f"push_to_tablet: [{a['severity']}] {a['description'][:100]}", "alert")
        db.log_alerts(ctrl.active_alerts[-1])
        yield _entry("DatabaseController", "DatabaseController → Data Store",
                     f"log_alerts(Alert[{a['severity']}]) — conflict in zone='{zone_id}'", "db")
    else:
        yield _entry("ConflictDetection", "", "Conflict score below threshold — no alert.", "info")

    yield _entry("DONE", "", "", "done")


# ── 5. Equipment Usage Reporting ──────────────────────────────────────────────

async def run_equipment_usage() -> AsyncIterator[dict]:
    db, dd, ctrl = _init_components()
    zone_id = "zone_b"
    member_id = "member_001"

    from backend.sensor.sensor_driver import EquipmentDriver
    from backend.sensor.sensor_interface import SensorInterface
    from backend.db.database_controller import EquipmentData
    from backend.reporting.usage_report_generator import UsageReportGenerator

    machines = [
        ("bench_press_01", 12, 60.0),
        ("cable_row_01", 15, 45.0),
        ("leg_press_01", 10, 80.0),
    ]

    sensor_interface = SensorInterface()

    for machine_id, reps, resistance in machines:
        driver = EquipmentDriver(
            machine_id=machine_id, zone_id=zone_id,
            member_id=member_id, reps=reps, resistance=resistance,
        )
        raw = driver.read()

        yield _entry("EquipmentDriver", "EquipmentDriver → SensorInterface",
                     f"read() — machine='{machine_id}', member='{member_id}', tap-in signal")
        await asyncio.sleep(0.3)

        event = sensor_interface.normalize_signal(raw)
        yield _entry("SensorInterface", "SensorInterface → DatabaseController",
                     f"normalize_signal → Event(type='equipment', reps={reps}, resistance={resistance} lbs)")
        await asyncio.sleep(0.3)

        eq_data = EquipmentData(
            member_id=event.member_id, machine_id=event.payload["machine_id"],
            zone_id=event.zone_id, reps=event.payload["reps"],
            resistance=event.payload["resistance"],
        )
        db.log_weight_lifting(eq_data)
        yield _entry("DatabaseController", "DatabaseController → Data Store",
                     f"log_weight_lifting(EquipmentData) — {reps} reps @ {resistance} lbs on '{machine_id}'", "db")
        await asyncio.sleep(0.3)

    yield _entry("UsageReportGenerator", "UsageReportGenerator → DatabaseController",
                 "generate('daily') — querying equipment usage data...")
    await asyncio.sleep(0.4)

    report_gen = UsageReportGenerator(database_controller=db)
    report = report_gen.generate("daily")
    ranking = report["equipment_summary"]["usage_ranking"]
    yield _entry("UsageReportGenerator", "UsageReportGenerator → Management Dashboard",
                 f"Report generated: {len(ranking)} machines, {report['equipment_summary']['total_sessions']} sessions total",
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


async def run(demo_name: str) -> AsyncIterator[dict]:
    if demo_name not in DEMOS:
        yield _entry("Error", "", f"Unknown demo: '{demo_name}'. Valid: {list(DEMOS.keys())}", "error")
        return
    try:
        async for entry in DEMOS[demo_name]():
            yield entry
    except Exception as exc:
        logger.exception("Demo '%s' failed", demo_name)
        yield _entry("Error", "", f"Demo error: {exc}", "error")
        yield _entry("DONE", "", "", "done")


def get_db_state() -> dict:
    """Return current DB state for the demos page database viewer."""
    if _db is None:
        _init_components()
    return _db.get_full_state()
