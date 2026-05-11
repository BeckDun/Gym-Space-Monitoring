from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from backend.db.database_controller import DatabaseController, QueryRequest

logger = logging.getLogger(__name__)

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
