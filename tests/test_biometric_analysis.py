"""Unit tests for BiometricAnalysis (SAD §3 Biometric Analysis)."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, call
from datetime import datetime

from backend.processing.biometric_analysis import BiometricAnalysis, BiometricStatus, HealthProfile
from backend.sensor.sensor_interface import Event


def _profile(low=50.0, high=160.0):
    return HealthProfile(
        member_id="m1",
        age=35,
        bmi=24.0,
        activity_level="moderate",
        heart_rate_threshold_low=low,
        heart_rate_threshold_high=high,
    )


def _controller():
    return MagicMock()


class TestEvaluateHeartRate:
    """SAD: evaluateHeartRate(float currentHeartRate, HealthProfile profile) → BiometricStatus"""

    def test_normal_heart_rate(self):
        ba = BiometricAnalysis(_controller())
        assert ba.evaluate_heart_rate(80.0, _profile()) == BiometricStatus.NORMAL

    def test_exactly_at_low_threshold_is_normal(self):
        ba = BiometricAnalysis(_controller())
        assert ba.evaluate_heart_rate(50.0, _profile(low=50.0)) == BiometricStatus.NORMAL

    def test_exactly_at_high_threshold_is_normal(self):
        ba = BiometricAnalysis(_controller())
        assert ba.evaluate_heart_rate(160.0, _profile(high=160.0)) == BiometricStatus.NORMAL

    def test_below_low_threshold_is_warning(self):
        ba = BiometricAnalysis(_controller())
        assert ba.evaluate_heart_rate(40.0, _profile(low=50.0)) == BiometricStatus.WARNING

    def test_above_high_threshold_is_warning(self):
        ba = BiometricAnalysis(_controller())
        assert ba.evaluate_heart_rate(185.0, _profile(high=160.0)) == BiometricStatus.WARNING

    def test_updates_instance_thresholds_from_profile(self):
        ba = BiometricAnalysis(_controller())
        profile = _profile(low=55.0, high=175.0)
        ba.evaluate_heart_rate(100.0, profile)
        assert ba.heart_rate_threshold_low == 55.0
        assert ba.heart_rate_threshold_high == 175.0

    def test_sets_current_profile(self):
        ba = BiometricAnalysis(_controller())
        profile = _profile()
        ba.evaluate_heart_rate(90.0, profile)
        assert ba.current_profile is profile


class TestTriggerAlert:
    """SAD: triggerAlert(BiometricStatus, MemberID, ZoneID) calls SystemController.receive_alert_trigger."""

    def test_warning_status_calls_controller(self):
        ctrl = _controller()
        ba = BiometricAnalysis(ctrl)
        ba.trigger_alert(BiometricStatus.WARNING, "m1", "cardio_zone", current_heart_rate=185.0)
        ctrl.receive_alert_trigger.assert_called_once()

    def test_normal_status_does_not_call_controller(self):
        ctrl = _controller()
        ba = BiometricAnalysis(ctrl)
        ba.trigger_alert(BiometricStatus.NORMAL, "m1", "cardio_zone")
        ctrl.receive_alert_trigger.assert_not_called()

    def test_alert_event_contains_member_id(self):
        ctrl = _controller()
        ba = BiometricAnalysis(ctrl)
        ba.trigger_alert(BiometricStatus.WARNING, "m42", "smart_machine_zone", 200.0)
        event = ctrl.receive_alert_trigger.call_args[0][0]
        assert event.member_id == "m42"
        assert event.zone_id == "smart_machine_zone"

    def test_alert_payload_severity_is_warning(self):
        ctrl = _controller()
        ba = BiometricAnalysis(ctrl)
        ba.trigger_alert(BiometricStatus.WARNING, "m1", "cardio_zone", 50.0)
        event = ctrl.receive_alert_trigger.call_args[0][0]
        assert event.payload["severity"] == "WARNING"


class TestProcessEvent:
    def test_process_event_triggers_alert_for_abnormal_hr(self):
        ctrl = _controller()
        ba = BiometricAnalysis(ctrl)
        event = Event(
            type="biometric",
            payload={"heart_rate": 200.0},
            zone_id="cardio_zone",
            member_id="m1",
            timestamp=datetime.utcnow(),
        )
        ba.process_event(event, _profile(high=160.0))
        ctrl.receive_alert_trigger.assert_called_once()

    def test_process_event_no_alert_for_normal_hr(self):
        ctrl = _controller()
        ba = BiometricAnalysis(ctrl)
        event = Event(
            type="biometric",
            payload={"heart_rate": 100.0},
            zone_id="cardio_zone",
            member_id="m1",
            timestamp=datetime.utcnow(),
        )
        ba.process_event(event, _profile())
        ctrl.receive_alert_trigger.assert_not_called()

    def test_process_event_no_heart_rate_key_is_no_op(self):
        ctrl = _controller()
        ba = BiometricAnalysis(ctrl)
        event = Event(type="biometric", payload={}, zone_id="cardio_zone", member_id="m1", timestamp=datetime.utcnow())
        ba.process_event(event, _profile())
        ctrl.receive_alert_trigger.assert_not_called()
