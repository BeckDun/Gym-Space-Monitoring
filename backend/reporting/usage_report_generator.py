from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from backend.db.database_controller import DatabaseController, QueryRequest

logger = logging.getLogger(__name__)

# ── AI insights prompt ────────────────────────────────────────────────────────

_INSIGHTS_PROMPT = """\
You are a professional gym operations consultant. A gym management system has \
collected the following usage data for the period specified. Analyse it and return \
a concise, actionable management report with THREE sections exactly as shown below. \
Use bullet points inside each section.

## Equipment Recommendations
Identify the most-used machines (candidates for adding more units) and the \
least-used (candidates for removal or repositioning). Be specific about machine IDs.

## Zone Optimization
Identify which zones are overcrowded or approaching capacity and give concrete \
suggestions for redistributing members or expanding/reconfiguring those spaces.

## Safety & Alert Patterns
Highlight recurring alert types, unresolved issues, or members who appear \
repeatedly in alerts and suggest preventive actions.

---
DATA:
{data}
---
Keep each bullet point under 25 words. Do not add extra sections.
"""

_SCHEDULE_DELTAS = {
    "hourly": timedelta(hours=1),
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
    "monthly": timedelta(days=30),
}


class UsageReportGenerator:
    """
    Accesses historical data logged by the DatabaseController to compile
    management usage reports. SAD: MLLM (Usage Report Generator).
    """

    def __init__(self, database_controller: DatabaseController) -> None:
        self._db = database_controller

    def generate(self, schedule: str) -> dict:
        """
        Compile a management usage report for the given schedule window.
        Calls DatabaseController.handle_report_query() for each data type.
        """
        if schedule not in _SCHEDULE_DELTAS:
            raise ValueError(f"Unknown schedule: {schedule!r}. Use one of {list(_SCHEDULE_DELTAS)}")

        end_time = datetime.utcnow()
        start_time = end_time - _SCHEDULE_DELTAS[schedule]

        logger.info("Generating %s report: %s → %s", schedule, start_time.isoformat(), end_time.isoformat())

        equipment_data = self._db.handle_report_query(QueryRequest("equipment", start_time, end_time))
        occupancy_data = self._db.handle_report_query(QueryRequest("occupancy", start_time, end_time))
        alert_data = self._db.handle_report_query(QueryRequest("alerts", start_time, end_time))

        result = {
            "schedule": schedule,
            "generated_at": end_time.isoformat(),
            "period_start": start_time.isoformat(),
            "period_end": end_time.isoformat(),
            "equipment_summary": self._summarize_equipment(equipment_data["records"]),
            "occupancy_summary": self._summarize_occupancy(occupancy_data["records"]),
            "alert_summary": self._summarize_alerts(alert_data["records"]),
        }
        # If running in mock mode and no real data exists, supplement with demo data
        from backend.config import USE_MOCK_MLLM
        no_equipment = result["equipment_summary"]["total_sessions"] == 0
        no_occupancy = result["occupancy_summary"]["peak_count"] == 0
        if USE_MOCK_MLLM and no_equipment and no_occupancy:
            return self._mock_report(schedule, start_time, end_time)
        return result

    def _mock_report(self, schedule: str, start_time: datetime, end_time: datetime) -> dict:
        """Return a realistic demo gym usage report when no real data exists."""
        mock_alerts = [
            {
                "alert_id": "mock_001",
                "severity": "CRITICAL",
                "zone_id": "cardio_zone",
                "description": "Member fall detected in Cardio Zone — immediate response required.",
                "member_id": "member_003",
                "resolved": True,
                "created_at": (end_time - timedelta(hours=3, minutes=22)).isoformat(),
            },
            {
                "alert_id": "mock_002",
                "severity": "CRITICAL",
                "zone_id": "smart_machine_zone",
                "description": "Member conflict detected — two members in physical altercation.",
                "member_id": "member_005",
                "resolved": True,
                "created_at": (end_time - timedelta(hours=1, minutes=45)).isoformat(),
            },
            {
                "alert_id": "mock_003",
                "severity": "WARNING",
                "zone_id": "cardio_zone",
                "description": "Abnormal heart rate: 181 bpm exceeds threshold of 165 bpm for member_001.",
                "member_id": "member_001",
                "resolved": True,
                "created_at": (end_time - timedelta(hours=5, minutes=10)).isoformat(),
            },
            {
                "alert_id": "mock_004",
                "severity": "WARNING",
                "zone_id": "functional_zone",
                "description": "Zone overcrowding: 23/20 members — approaching capacity limit.",
                "member_id": None,
                "resolved": True,
                "created_at": (end_time - timedelta(hours=2, minutes=30)).isoformat(),
            },
            {
                "alert_id": "mock_005",
                "severity": "WARNING",
                "zone_id": "cycling_zone",
                "description": "Abnormal heart rate: 196 bpm exceeds threshold of 180 bpm for member_007.",
                "member_id": "member_007",
                "resolved": False,
                "created_at": (end_time - timedelta(minutes=18)).isoformat(),
            },
            {
                "alert_id": "mock_006",
                "severity": "WARNING",
                "zone_id": "smart_machine_zone",
                "description": "Zone overcrowding: 27/25 members — capacity exceeded.",
                "member_id": None,
                "resolved": False,
                "created_at": (end_time - timedelta(minutes=7)).isoformat(),
            },
            {
                "alert_id": "mock_007",
                "severity": "INFO",
                "zone_id": "entrance",
                "description": "Peak occupancy period detected — gym at 93% total capacity.",
                "member_id": None,
                "resolved": True,
                "created_at": (end_time - timedelta(hours=4)).isoformat(),
            },
            {
                "alert_id": "mock_008",
                "severity": "INFO",
                "zone_id": "cardio_zone",
                "description": "Equipment maintenance reminder: treadmill_03 due for service.",
                "member_id": None,
                "resolved": True,
                "created_at": (end_time - timedelta(hours=6, minutes=5)).isoformat(),
            },
        ]
        alert_summary = self._summarize_alerts(mock_alerts)

        return {
            "is_mock": True,
            "schedule": schedule,
            "generated_at": end_time.isoformat(),
            "period_start": start_time.isoformat(),
            "period_end": end_time.isoformat(),
            "equipment_summary": {
                "total_sessions": 47,
                "usage_ranking": [
                    {"machine_id": "bench_press_01", "sessions": 14, "total_reps": 168},
                    {"machine_id": "cable_row_01",   "sessions": 11, "total_reps": 165},
                    {"machine_id": "leg_press_01",   "sessions":  9, "total_reps":  90},
                    {"machine_id": "lat_pulldown_01","sessions":  7, "total_reps":  84},
                    {"machine_id": "shoulder_press_01","sessions": 6, "total_reps": 72},
                ],
            },
            "occupancy_summary": {
                "peak_count": 28,
                "average_count": 14.2,
                "smart_machine_zonereakdown": {
                    "cardio_zone":        {"peak": 28, "average": 16.4},
                    "smart_machine_zone": {"peak": 27, "average": 13.1},
                    "cycling_zone":       {"peak": 18, "average":  9.8},
                    "functional_zone":    {"peak": 23, "average": 11.5},
                },
            },
            "alert_summary": alert_summary,
        }

    def _summarize_equipment(self, records: list[dict]) -> dict:
        machine_usage: Counter = Counter()
        total_reps: defaultdict = defaultdict(int)
        for r in records:
            machine_usage[r["machine_id"]] += 1
            total_reps[r["machine_id"]] += r.get("reps", 0)

        ranked = sorted(machine_usage.items(), key=lambda x: x[1], reverse=True)
        return {
            "total_sessions": len(records),
            "usage_ranking": [{"machine_id": m, "sessions": c, "total_reps": total_reps[m]} for m, c in ranked],
        }

    def _summarize_occupancy(self, records: list[dict]) -> dict:
        if not records:
            return {"peak_count": 0, "average_count": 0, "smart_machine_zonereakdown": {}}

        cycling_zoneounts: defaultdict = defaultdict(list)
        for r in records:
            cycling_zoneounts[r["zone_id"]].append(r["count"])

        smart_machine_zonereakdown = {
            zone: {"peak": max(counts), "average": round(sum(counts) / len(counts), 1)}
            for zone, counts in cycling_zoneounts.items()
        }
        all_counts = [r["count"] for r in records]
        return {
            "peak_count": max(all_counts),
            "average_count": round(sum(all_counts) / len(all_counts), 1),
            "smart_machine_zonereakdown": smart_machine_zonereakdown,
        }

    def _summarize_alerts(self, records: list[dict]) -> dict:
        by_severity: Counter = Counter(r["severity"] for r in records)
        resolved = sum(1 for r in records if r.get("resolved"))
        return {
            "total": len(records),
            "critical": by_severity.get("CRITICAL", 0),
            "warning": by_severity.get("WARNING", 0),
            "info": by_severity.get("INFO", 0),
            "resolved": resolved,
            "unresolved": len(records) - resolved,
            "records": records,  # individual alert records for clickable alert history
        }

    # ── AI insights ───────────────────────────────────────────────────────────

    def generate_ai_insights(self, report: dict) -> dict:
        """
        Pass the compiled report to Gemini and return structured AI insights.
        Falls back to a mock response when no API key is configured.
        """
        from backend.config import GEMINI_API_KEY, MLLM_MODEL, USE_MOCK_MLLM

        # Strip raw alert records from the payload — too verbose for the prompt
        slim = {
            "schedule": report.get("schedule"),
            "period_start": report.get("period_start"),
            "period_end": report.get("period_end"),
            "equipment_summary": {
                k: v for k, v in report.get("equipment_summary", {}).items()
                if k != "records"
            },
            "occupancy_summary": report.get("occupancy_summary", {}),
            "alert_summary": {
                k: v for k, v in report.get("alert_summary", {}).items()
                if k != "records"
            },
        }
        data_str = json.dumps(slim, indent=2)

        if USE_MOCK_MLLM:
            return self._mock_ai_insights(slim)

        try:
            from google import genai
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = _INSIGHTS_PROMPT.format(data=data_str)
            response = client.models.generate_content(model=MLLM_MODEL, contents=prompt)
            return {"success": True, "text": response.text}
        except Exception as exc:
            logger.error("AI insights generation failed: %s", exc)
            return {"success": False, "error": str(exc)}

    def _mock_ai_insights(self, slim: dict) -> dict:
        """Deterministic mock response derived from the actual report data."""
        eq = slim.get("equipment_summary", {})
        occ = slim.get("occupancy_summary", {})
        al = slim.get("alert_summary", {})
        ranking = eq.get("usage_ranking", [])
        breakdown = occ.get("smart_machine_zonereakdown", {})

        top = ranking[0]["machine_id"] if ranking else "bench_press_01"
        bottom = ranking[-1]["machine_id"] if len(ranking) > 1 else "lat_pulldown_01"
        hotzone = max(breakdown, key=lambda z: breakdown[z].get("peak", 0), default="cardio_zone") \
            if breakdown else "cardio_zone"
        hotpeak = breakdown.get(hotzone, {}).get("peak", occ.get("peak_count", "?"))

        text = f"""\
## Equipment Recommendations
- **{top}** is the most-used machine — consider adding a second unit to reduce wait times.
- **{bottom}** has low utilisation — evaluate repositioning it to a higher-traffic area.
- Machines with < 5 sessions in the period should be reviewed for removal or replacement.
- Rotate underused machines to peak-hour zones to balance member flow.

## Zone Optimization
- **{hotzone}** hit a peak of {hotpeak} members — exceeding the capacity of 5; consider splitting this zone or adding queue management.
- Introduce signage and staff guidance during peak hours to redirect members to lower-occupancy zones.
- Evaluate converting underused floor space in low-traffic zones to expand high-demand areas.
- Consider staggered entry scheduling if peak overcrowding recurs across multiple time slots.

## Safety & Alert Patterns
- {al.get("unresolved", 0)} alert(s) remain unresolved — prioritise review before the next session.
- {al.get("warning", 0)} WARNING-level biometric alerts logged; follow up with affected members.
- Recurring overcrowding in the same zone suggests a structural capacity issue, not a one-off event.
- Ensure all CRITICAL alerts (falls, conflicts) trigger an immediate staff presence protocol.\
"""
        return {"success": True, "text": text, "is_mock": True}
