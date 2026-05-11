"""Unit tests for UsageReportGenerator (SAD §3 MLLM Usage Report Generator)."""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock


def _make_generator(equipment=None, occupancy=None, alerts=None):
    from backend.reporting.usage_report_generator import UsageReportGenerator
    db = MagicMock()
    db.handle_report_query.side_effect = lambda q: {
        "equipment": {"report_type": "equipment", "records": equipment or []},
        "occupancy": {"report_type": "occupancy", "records": occupancy or []},
        "alerts": {"report_type": "alerts", "records": alerts or []},
    }[q.report_type]
    return UsageReportGenerator(database_controller=db), db


class TestSummarizeEquipment:
    def test_empty_records_returns_zero_sessions(self):
        gen, _ = _make_generator()
        result = gen._summarize_equipment([])
        assert result["total_sessions"] == 0
        assert result["usage_ranking"] == []

    def test_counts_sessions_per_machine(self):
        gen, _ = _make_generator()
        records = [
            {"machine_id": "press_01", "reps": 10, "resistance": 50},
            {"machine_id": "press_01", "reps": 8, "resistance": 50},
            {"machine_id": "squat_01", "reps": 5, "resistance": 80},
        ]
        result = gen._summarize_equipment(records)
        ranking = {r["machine_id"]: r["sessions"] for r in result["usage_ranking"]}
        assert ranking["press_01"] == 2
        assert ranking["squat_01"] == 1

    def test_ranking_sorted_descending(self):
        gen, _ = _make_generator()
        records = [
            {"machine_id": "a", "reps": 1, "resistance": 10},
            {"machine_id": "b", "reps": 1, "resistance": 10},
            {"machine_id": "b", "reps": 1, "resistance": 10},
            {"machine_id": "b", "reps": 1, "resistance": 10},
        ]
        result = gen._summarize_equipment(records)
        assert result["usage_ranking"][0]["machine_id"] == "b"

    def test_total_reps_summed(self):
        gen, _ = _make_generator()
        records = [
            {"machine_id": "press_01", "reps": 10, "resistance": 50},
            {"machine_id": "press_01", "reps": 8, "resistance": 50},
        ]
        result = gen._summarize_equipment(records)
        assert result["usage_ranking"][0]["total_reps"] == 18


class TestSummarizeOccupancy:
    def test_empty_returns_zeros(self):
        gen, _ = _make_generator()
        result = gen._summarize_occupancy([])
        assert result["peak_count"] == 0
        assert result["average_count"] == 0

    def test_peak_count(self):
        gen, _ = _make_generator()
        records = [
            {"zone_id": "cardio_zone", "count": 10, "timestamp": "2024-01-01T10:00"},
            {"zone_id": "cardio_zone", "count": 25, "timestamp": "2024-01-01T11:00"},
            {"zone_id": "cardio_zone", "count": 15, "timestamp": "2024-01-01T12:00"},
        ]
        result = gen._summarize_occupancy(records)
        assert result["peak_count"] == 25

    def test_average_count(self):
        gen, _ = _make_generator()
        records = [
            {"zone_id": "cardio_zone", "count": 10, "timestamp": "t"},
            {"zone_id": "cardio_zone", "count": 20, "timestamp": "t"},
        ]
        result = gen._summarize_occupancy(records)
        assert result["average_count"] == 15.0

    def test_smart_machine_zonereakdown_present(self):
        gen, _ = _make_generator()
        records = [
            {"zone_id": "cardio_zone", "count": 10, "timestamp": "t"},
            {"zone_id": "smart_machine_zone", "count": 5, "timestamp": "t"},
        ]
        result = gen._summarize_occupancy(records)
        assert "cardio_zone" in result["smart_machine_zonereakdown"]
        assert "smart_machine_zone" in result["smart_machine_zonereakdown"]


class TestSummarizeAlerts:
    def test_empty_returns_zeros(self):
        gen, _ = _make_generator()
        result = gen._summarize_alerts([])
        assert result["total"] == 0
        assert result["critical"] == 0

    def test_counts_by_severity(self):
        gen, _ = _make_generator()
        records = [
            {"severity": "CRITICAL", "resolved": False},
            {"severity": "CRITICAL", "resolved": True},
            {"severity": "WARNING", "resolved": False},
            {"severity": "INFO", "resolved": True},
        ]
        result = gen._summarize_alerts(records)
        assert result["critical"] == 2
        assert result["warning"] == 1
        assert result["info"] == 1

    def test_resolved_vs_unresolved(self):
        gen, _ = _make_generator()
        records = [
            {"severity": "CRITICAL", "resolved": True},
            {"severity": "WARNING", "resolved": False},
            {"severity": "WARNING", "resolved": False},
        ]
        result = gen._summarize_alerts(records)
        assert result["resolved"] == 1
        assert result["unresolved"] == 2


class TestGenerate:
    def test_generate_calls_db_three_times(self):
        gen, db = _make_generator()
        gen.generate("hourly")
        assert db.handle_report_query.call_count == 3

    def test_generate_invalid_schedule_raises(self):
        gen, _ = _make_generator()
        with pytest.raises(ValueError, match="Unknown schedule"):
            gen.generate("quarterly")

    def test_generate_returns_schedule_key(self):
        gen, _ = _make_generator()
        result = gen.generate("daily")
        assert result["schedule"] == "daily"
        assert "generated_at" in result
        assert "equipment_summary" in result
        assert "occupancy_summary" in result
        assert "alert_summary" in result
