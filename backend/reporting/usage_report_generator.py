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

        return {
            "schedule": schedule,
            "generated_at": end_time.isoformat(),
            "period_start": start_time.isoformat(),
            "period_end": end_time.isoformat(),
            "equipment_summary": self._summarize_equipment(equipment_data["records"]),
            "occupancy_summary": self._summarize_occupancy(occupancy_data["records"]),
            "alert_summary": self._summarize_alerts(alert_data["records"]),
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
            return {"peak_count": 0, "average_count": 0, "zone_breakdown": {}}

        zone_counts: defaultdict = defaultdict(list)
        for r in records:
            zone_counts[r["zone_id"]].append(r["count"])

        zone_breakdown = {
            zone: {"peak": max(counts), "average": round(sum(counts) / len(counts), 1)}
            for zone, counts in zone_counts.items()
        }
        all_counts = [r["count"] for r in records]
        return {
            "peak_count": max(all_counts),
            "average_count": round(sum(all_counts) / len(all_counts), 1),
            "zone_breakdown": zone_breakdown,
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
        }
