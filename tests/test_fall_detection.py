"""Unit tests for FallDetection (SAD §3 Fall Detection)."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


def _make_fd(threshold=6.0):
    from backend.processing.fall_detection import FallDetection
    ctrl = MagicMock()
    with patch("backend.processing.fall_detection.FALL_CONFIDENCE_THRESHOLD", threshold):
        fd = FallDetection(system_controller=ctrl)
    return fd, ctrl


class TestParseScore:
    from backend.processing.fall_detection import FallDetection

    def test_parses_integer_fall_score(self):
        from backend.processing.fall_detection import FallDetection
        assert FallDetection._parse_score("Fall: 8, Confidence: 9", "Fall") == 8.0

    def test_parses_float_fall_score(self):
        from backend.processing.fall_detection import FallDetection
        assert FallDetection._parse_score("Fall: 7.5, Confidence: 8", "Fall") == 7.5

    def test_returns_zero_when_not_found(self):
        from backend.processing.fall_detection import FallDetection
        assert FallDetection._parse_score("No relevant data here", "Fall") == 0.0

    def test_case_insensitive(self):
        from backend.processing.fall_detection import FallDetection
        assert FallDetection._parse_score("fall: 5", "Fall") == 5.0

    def test_parses_confidence_key(self):
        from backend.processing.fall_detection import FallDetection
        assert FallDetection._parse_score("Fall: 8, Confidence: 9", "Confidence") == 9.0


class TestAnalyzeMLLMOutput:
    """SAD: analyzeMLLMOutput(String mllmTextOutput) identifies fall patterns."""

    def test_critical_alert_above_threshold(self):
        fd, ctrl = _make_fd(threshold=6.0)
        fd.analyze_mllm_output("Fall: 8, Confidence: 9", "zone_a")
        ctrl.receive_alert_trigger.assert_called_once()
        event = ctrl.receive_alert_trigger.call_args[0][0]
        assert event.payload["severity"] == "CRITICAL"

    def test_warning_alert_between_4_and_threshold(self):
        fd, ctrl = _make_fd(threshold=6.0)
        fd.analyze_mllm_output("Fall: 5, Confidence: 6", "zone_a")
        ctrl.receive_alert_trigger.assert_called_once()
        event = ctrl.receive_alert_trigger.call_args[0][0]
        assert event.payload["severity"] == "WARNING"

    def test_no_alert_below_4(self):
        fd, ctrl = _make_fd(threshold=6.0)
        fd.analyze_mllm_output("Fall: 3, Confidence: 2", "zone_a")
        ctrl.receive_alert_trigger.assert_not_called()

    def test_no_alert_when_score_zero(self):
        fd, ctrl = _make_fd(threshold=6.0)
        fd.analyze_mllm_output("No fall detected", "zone_a")
        ctrl.receive_alert_trigger.assert_not_called()

    def test_stores_mllm_text_output(self):
        fd, _ = _make_fd()
        fd.analyze_mllm_output("Fall: 8, Confidence: 9", "zone_a")
        assert fd.mllm_text_output == "Fall: 8, Confidence: 9"

    def test_critical_at_exactly_threshold(self):
        fd, ctrl = _make_fd(threshold=6.0)
        fd.analyze_mllm_output("Fall: 6, Confidence: 7", "zone_a")
        event = ctrl.receive_alert_trigger.call_args[0][0]
        assert event.payload["severity"] == "CRITICAL"


class TestTriggerAlert:
    """SAD: triggerAlert(AlertSeverity, ZoneID) passes event to SystemController."""

    def test_trigger_creates_alert_event(self):
        fd, ctrl = _make_fd()
        fd.mllm_text_output = "Fall: 8, Confidence: 9"
        fd.trigger_alert("CRITICAL", "zone_b")
        ctrl.receive_alert_trigger.assert_called_once()

    def test_trigger_sets_zone_id(self):
        fd, ctrl = _make_fd()
        fd.mllm_text_output = "Fall: 8, Confidence: 9"
        fd.trigger_alert("CRITICAL", "zone_c")
        event = ctrl.receive_alert_trigger.call_args[0][0]
        assert event.zone_id == "zone_c"
