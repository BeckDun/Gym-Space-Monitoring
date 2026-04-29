"""Unit tests for SystemController (SAD §3 System Controller)."""
from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import MagicMock, call

from backend.controller.system_controller import SystemController
from backend.sensor.device_driver import Alert, DeviceDriver
from backend.sensor.sensor_interface import Event


def _event(severity="CRITICAL", description="Test alert", zone="zone_a", member=None, type_="alert"):
    return Event(
        type=type_,
        payload={"severity": severity, "description": description},
        zone_id=zone,
        member_id=member,
        timestamp=datetime.utcnow(),
    )


def _make_controller():
    device_driver = MagicMock(spec=DeviceDriver)
    db = MagicMock()
    ctrl = SystemController(device_driver=device_driver, database_controller=db)
    return ctrl, device_driver, db


class TestReceiveAlertTrigger:
    """SAD: receiveAlertTrigger(Event) — primary sink for all monitoring modules."""

    def test_adds_alert_to_active_alerts(self):
        ctrl, _, _ = _make_controller()
        ctrl.receive_alert_trigger(_event())
        assert len(ctrl.active_alerts) == 1

    def test_alert_severity_matches_event(self):
        ctrl, _, _ = _make_controller()
        ctrl.receive_alert_trigger(_event(severity="WARNING"))
        assert ctrl.active_alerts[0].severity == "WARNING"

    def test_alert_zone_id_matches_event(self):
        ctrl, _, _ = _make_controller()
        ctrl.receive_alert_trigger(_event(zone="zone_b"))
        assert ctrl.active_alerts[0].zone_id == "zone_b"

    def test_calls_dispatch_alert(self):
        ctrl, device_driver, _ = _make_controller()
        ctrl.receive_alert_trigger(_event())
        device_driver.push_to_tablet.assert_called_once()

    def test_multiple_alerts_accumulate(self):
        ctrl, _, _ = _make_controller()
        ctrl.receive_alert_trigger(_event(zone="zone_a"))
        ctrl.receive_alert_trigger(_event(zone="zone_b"))
        ctrl.receive_alert_trigger(_event(zone="zone_c"))
        assert len(ctrl.active_alerts) == 3


class TestDispatchAlert:
    """SAD: dispatchAlert(Alert) — routes to DeviceDriver."""

    def test_pushes_to_tablet(self):
        ctrl, dd, _ = _make_controller()
        alert = Alert(severity="CRITICAL", zone_id="zone_a", description="Fall detected")
        ctrl.dispatch_alert(alert)
        dd.push_to_tablet.assert_called_once_with(alert)

    def test_heart_rate_warning_also_pushes_to_wristband(self):
        ctrl, dd, _ = _make_controller()
        alert = Alert(severity="WARNING", zone_id="zone_a", description="Abnormal heart rate detected for member m1", member_id="m1")
        ctrl.dispatch_alert(alert)
        dd.push_to_tablet.assert_called_once()
        assert dd.push_to_wristband.call_count == 1
        assert dd.push_to_wristband.call_args[0][0] == "m1"

    def test_critical_alert_does_not_push_to_wristband(self):
        ctrl, dd, _ = _make_controller()
        alert = Alert(severity="CRITICAL", zone_id="zone_a", description="Fall detected")
        ctrl.dispatch_alert(alert)
        dd.push_to_wristband.assert_not_called()

    def test_non_heart_rate_warning_no_wristband(self):
        ctrl, dd, _ = _make_controller()
        alert = Alert(severity="WARNING", zone_id="zone_a", description="Zone overcrowded: 31/30", member_id=None)
        ctrl.dispatch_alert(alert)
        dd.push_to_wristband.assert_not_called()


class TestResolveAlert:
    """SAD Fall Detection step 8: staff resolves → controller logs resolution."""

    def test_resolve_existing_alert_returns_true(self):
        ctrl, _, _ = _make_controller()
        ctrl.receive_alert_trigger(_event())
        alert_id = ctrl.active_alerts[0].alert_id
        assert ctrl.resolve_alert(alert_id) is True

    def test_resolve_removes_from_active_alerts(self):
        ctrl, _, db = _make_controller()
        ctrl.receive_alert_trigger(_event())
        alert_id = ctrl.active_alerts[0].alert_id
        ctrl.resolve_alert(alert_id)
        assert len(ctrl.active_alerts) == 0

    def test_resolve_logs_to_db(self):
        ctrl, _, db = _make_controller()
        ctrl.receive_alert_trigger(_event())
        alert_id = ctrl.active_alerts[0].alert_id
        ctrl.resolve_alert(alert_id)
        db.log_alerts.assert_called()

    def test_resolve_nonexistent_alert_returns_false(self):
        ctrl, _, _ = _make_controller()
        assert ctrl.resolve_alert("nonexistent-id") is False

    def test_resolved_alert_marked_as_resolved(self):
        ctrl, _, db = _make_controller()
        ctrl.receive_alert_trigger(_event())
        alert_id = ctrl.active_alerts[0].alert_id
        ctrl.resolve_alert(alert_id)
        logged_alert = db.log_alerts.call_args[0][0]
        assert logged_alert.resolved is True


class TestGetActiveAlerts:
    def test_returns_list_of_dicts(self):
        ctrl, _, _ = _make_controller()
        ctrl.receive_alert_trigger(_event())
        alerts = ctrl.get_active_alerts()
        assert isinstance(alerts, list)
        assert "alert_id" in alerts[0]
        assert "severity" in alerts[0]

    def test_empty_when_no_alerts(self):
        ctrl, _, _ = _make_controller()
        assert ctrl.get_active_alerts() == []
