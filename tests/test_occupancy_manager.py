"""Unit tests for OccupancyManager (SAD §3 Occupancy Manager)."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


def _make_manager(thresholds=None):
    from backend.processing.occupancy_manager import OccupancyManager
    ctrl = MagicMock()
    with patch("backend.processing.occupancy_manager.ZONE_THRESHOLDS", thresholds or {"zone_a": 5, "zone_b": 3}):
        om = OccupancyManager(system_controller=ctrl)
    return om, ctrl


class TestUpdateLocationDensity:
    """SAD: updateLocationDensity(MemberID, ZoneID) updates zone_occupancy_counts."""

    def test_first_entry_sets_count_to_one(self):
        om, _ = _make_manager()
        om.update_location_density("m1", "zone_a")
        assert om.zone_occupancy_counts["zone_a"] == 1

    def test_multiple_members_accumulate(self):
        om, _ = _make_manager()
        om.update_location_density("m1", "zone_a")
        om.update_location_density("m2", "zone_a")
        om.update_location_density("m3", "zone_a")
        assert om.zone_occupancy_counts["zone_a"] == 3

    def test_moving_member_decrements_old_zone(self):
        om, _ = _make_manager()
        om.update_location_density("m1", "zone_a")
        om.update_location_density("m2", "zone_a")
        om.update_location_density("m1", "zone_b")  # m1 moves
        assert om.zone_occupancy_counts["zone_a"] == 1
        assert om.zone_occupancy_counts["zone_b"] == 1

    def test_same_zone_update_does_not_double_count(self):
        om, _ = _make_manager()
        om.update_location_density("m1", "zone_a")
        om.update_location_density("m1", "zone_a")  # same zone, same member
        assert om.zone_occupancy_counts["zone_a"] == 1


class TestVerifyThreshold:
    """SAD: verifyThreshold(ZoneID) evaluates count against zoneOccupancyThresholds."""

    def test_no_alert_below_80_percent(self):
        om, ctrl = _make_manager({"zone_a": 10})
        om.zone_occupancy_counts["zone_a"] = 7  # 70%
        om.verify_threshold("zone_a")
        ctrl.receive_alert_trigger.assert_not_called()

    def test_info_alert_at_80_percent(self):
        om, ctrl = _make_manager({"zone_a": 10})
        om.zone_occupancy_counts["zone_a"] = 8  # 80%
        om.verify_threshold("zone_a")
        ctrl.receive_alert_trigger.assert_called_once()
        event = ctrl.receive_alert_trigger.call_args[0][0]
        assert event.payload["severity"] == "INFO"

    def test_warning_alert_at_threshold(self):
        om, ctrl = _make_manager({"zone_a": 5})
        om.zone_occupancy_counts["zone_a"] = 5  # 100%
        om.verify_threshold("zone_a")
        ctrl.receive_alert_trigger.assert_called_once()
        event = ctrl.receive_alert_trigger.call_args[0][0]
        assert event.payload["severity"] == "WARNING"

    def test_warning_alert_above_threshold(self):
        om, ctrl = _make_manager({"zone_a": 5})
        om.zone_occupancy_counts["zone_a"] = 7
        om.verify_threshold("zone_a")
        event = ctrl.receive_alert_trigger.call_args[0][0]
        assert event.payload["severity"] == "WARNING"


class TestTriggerAlert:
    """SAD: triggerAlert(ZoneID) notifies SystemController of overcrowding."""

    def test_trigger_calls_controller(self):
        om, ctrl = _make_manager()
        om.zone_occupancy_counts["zone_a"] = 6
        om.trigger_alert("zone_a", severity="WARNING")
        ctrl.receive_alert_trigger.assert_called_once()

    def test_alert_description_contains_zone(self):
        om, ctrl = _make_manager()
        om.zone_occupancy_counts["zone_a"] = 6
        om.trigger_alert("zone_a", severity="WARNING")
        event = ctrl.receive_alert_trigger.call_args[0][0]
        assert "zone_a" in event.payload["description"]

    def test_alert_zone_id_matches(self):
        om, ctrl = _make_manager()
        om.zone_occupancy_counts["zone_b"] = 4
        om.trigger_alert("zone_b", severity="WARNING")
        event = ctrl.receive_alert_trigger.call_args[0][0]
        assert event.zone_id == "zone_b"


class TestRemoveMember:
    def test_remove_decrements_zone_count(self):
        om, _ = _make_manager()
        om.update_location_density("m1", "zone_a")
        om.update_location_density("m2", "zone_a")
        om.remove_member("m1")
        assert om.zone_occupancy_counts["zone_a"] == 1

    def test_remove_unknown_member_is_safe(self):
        om, _ = _make_manager()
        om.remove_member("not_a_member")  # should not raise

    def test_count_never_goes_below_zero(self):
        om, _ = _make_manager()
        om.zone_occupancy_counts["zone_a"] = 0
        om._member_locations["m1"] = "zone_a"
        om.remove_member("m1")
        assert om.zone_occupancy_counts["zone_a"] == 0


class TestGetSnapshot:
    def test_snapshot_reflects_current_state(self):
        om, _ = _make_manager()
        om.update_location_density("m1", "zone_a")
        om.update_location_density("m2", "zone_b")
        snap = om.get_snapshot()
        assert snap["zone_a"] == 1
        assert snap["zone_b"] == 1

    def test_snapshot_is_a_copy(self):
        om, _ = _make_manager()
        om.update_location_density("m1", "zone_a")
        snap = om.get_snapshot()
        snap["zone_a"] = 999
        assert om.zone_occupancy_counts["zone_a"] == 1
