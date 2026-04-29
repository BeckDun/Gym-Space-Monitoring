"""Unit tests for ConflictDetection (SAD §3 Conflict Detection)."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


def _make_cd(threshold=6.0):
    from backend.processing.conflict_detection import ConflictDetection
    ctrl = MagicMock()
    with patch("backend.processing.conflict_detection.CONFLICT_CONFIDENCE_THRESHOLD", threshold):
        cd = ConflictDetection(system_controller=ctrl)
    return cd, ctrl


class TestParseScore:
    def test_parses_conflict_score(self):
        from backend.processing.conflict_detection import ConflictDetection
        assert ConflictDetection._parse_score("Conflict: 7, Confidence: 8", "Conflict") == 7.0

    def test_returns_zero_when_not_found(self):
        from backend.processing.conflict_detection import ConflictDetection
        assert ConflictDetection._parse_score("No conflict detected", "Conflict") == 0.0

    def test_parses_float_value(self):
        from backend.processing.conflict_detection import ConflictDetection
        assert ConflictDetection._parse_score("Conflict: 6.5, Confidence: 9", "Conflict") == 6.5


class TestAnalyzeMLLMOutput:
    """SAD: analyzeMLLMOutput(String) identifies potential physical altercations."""

    def test_critical_alert_above_threshold(self):
        cd, ctrl = _make_cd(threshold=6.0)
        cd.analyze_mllm_output("Conflict: 8, Confidence: 9", "zone_a")
        ctrl.receive_alert_trigger.assert_called_once()
        event = ctrl.receive_alert_trigger.call_args[0][0]
        assert event.payload["severity"] == "CRITICAL"

    def test_warning_alert_between_4_and_threshold(self):
        cd, ctrl = _make_cd(threshold=6.0)
        cd.analyze_mllm_output("Conflict: 5, Confidence: 5", "zone_a")
        event = ctrl.receive_alert_trigger.call_args[0][0]
        assert event.payload["severity"] == "WARNING"

    def test_no_alert_score_below_4(self):
        cd, ctrl = _make_cd(threshold=6.0)
        cd.analyze_mllm_output("Conflict: 2, Confidence: 3", "zone_a")
        ctrl.receive_alert_trigger.assert_not_called()

    def test_no_alert_no_parseable_output(self):
        cd, ctrl = _make_cd(threshold=6.0)
        cd.analyze_mllm_output("People are exercising normally.", "zone_a")
        ctrl.receive_alert_trigger.assert_not_called()

    def test_stores_mllm_text_output(self):
        cd, _ = _make_cd()
        cd.analyze_mllm_output("Conflict: 7, Confidence: 8", "zone_a")
        assert cd.mllm_text_output == "Conflict: 7, Confidence: 8"

    def test_critical_at_exactly_threshold(self):
        cd, ctrl = _make_cd(threshold=6.0)
        cd.analyze_mllm_output("Conflict: 6, Confidence: 7", "zone_a")
        event = ctrl.receive_alert_trigger.call_args[0][0]
        assert event.payload["severity"] == "CRITICAL"


class TestTriggerAlert:
    """SAD: triggerAlert(AlertSeverity, ZoneID) dispatches to SystemController."""

    def test_trigger_sends_event_to_controller(self):
        cd, ctrl = _make_cd()
        cd.mllm_text_output = "Conflict: 7, Confidence: 8"
        cd.trigger_alert("CRITICAL", "zone_b")
        ctrl.receive_alert_trigger.assert_called_once()

    def test_trigger_event_type_is_alert(self):
        cd, ctrl = _make_cd()
        cd.mllm_text_output = "Conflict: 7, Confidence: 8"
        cd.trigger_alert("WARNING", "zone_a")
        event = ctrl.receive_alert_trigger.call_args[0][0]
        assert event.type == "alert"
