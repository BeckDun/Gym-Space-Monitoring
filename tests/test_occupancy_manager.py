"""Unit tests for OccupancyManager (SAD §3 Occupancy Manager)."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


def _make_manager(thresholds=None):
    from backend.processing.occupancy_manager import OccupancyManager
    ctrl = MagicMock()
    with patch("backend.processing.occupancy_manager.ZONE_THRESHOLDS", thresholds or {"cardio_zone": 5, "smart_machine_zone": 3}):
        om = OccupancyManager(system_controller=ctrl)
    return om, ctrl


class TestUpdateLocationDensity:
    """SAD: updateLocationDensity(MemberID, ZoneID) updates zone_occupancy_counts."""

    def test_first_entry_sets_count_to_one(self):
        om, _ = _make_manager()
        om.update_location_density("m1", "cardio_zone")
        assert om.zone_occupancy_counts["cardio_zone"] == 1

    def test_multiple_members_accumulate(self):
        om, _ = _make_manager()
        om.update_location_density("m1", "cardio_zone")
        om.update_location_density("m2", "cardio_zone")
        om.update_location_density("m3", "cardio_zone")
        assert om.zone_occupancy_counts["cardio_zone"] == 3

    def test_moving_member_decrements_old_zone(self):
        om, _ = _make_manager()
        om.update_location_density("m1", "cardio_zone")
        om.update_location_density("m2", "cardio_zone")
        om.update_location_density("m1", "smart_machine_zone")  # m1 moves
        assert om.zone_occupancy_counts["cardio_zone"] == 1
        assert om.zone_occupancy_counts["smart_machine_zone"] == 1

    def test_same_zone_update_does_not_double_count(self):
        om, _ = _make_manager()
        om.update_location_density("m1", "cardio_zone")
        om.update_location_density("m1", "cardio_zone")  # same zone, same member
        assert om.zone_occupancy_counts["cardio_zone"] == 1


class TestVerifyThreshold:
    """SAD: verifyThreshold(ZoneID) evaluates count against zoneOccupancyThresholds."""

    def test_no_alert_below_80_percent(self):
        om, ctrl = _make_manager({"cardio_zone": 10})
        om.zone_occupancy_counts["cardio_zone"] = 7  # 70%
        om.verify_threshold("cardio_zone")
        ctrl.receive_alert_trigger.assert_not_called()

    def test_info_alert_at_80_percent(self):
        om, ctrl = _make_manager({"cardio_zone": 10})
        om.zone_occupancy_counts["cardio_zone"] = 8  # 80%
        om.verify_threshold("cardio_zone")
        ctrl.receive_alert_trigger.assert_called_once()
        event = ctrl.receive_alert_trigger.call_args[0][0]
        assert event.payload["severity"] == "INFO"

    def test_warning_alert_at_threshold(self):
        om, ctrl = _make_manager({"cardio_zone": 5})
        om.zone_occupancy_counts["cardio_zone"] = 5  # 100%
        om.verify_threshold("cardio_zone")
        ctrl.receive_alert_trigger.assert_called_once()
        event = ctrl.receive_alert_trigger.call_args[0][0]
        assert event.payload["severity"] == "WARNING"

    def test_warning_alert_above_threshold(self):
        om, ctrl = _make_manager({"cardio_zone": 5})
        om.zone_occupancy_counts["cardio_zone"] = 7
        om.verify_threshold("cardio_zone")
        event = ctrl.receive_alert_trigger.call_args[0][0]
        assert event.payload["severity"] == "WARNING"


class TestTriggerAlert:
    """SAD: triggerAlert(ZoneID) notifies SystemController of overcrowding."""

    def test_trigger_calls_controller(self):
        om, ctrl = _make_manager()
        om.zone_occupancy_counts["cardio_zone"] = 6
        om.trigger_alert("cardio_zone", severity="WARNING")
        ctrl.receive_alert_trigger.assert_called_once()

    def test_alert_description_contains_zone(self):
        om, ctrl = _make_manager()
        om.zone_occupancy_counts["cardio_zone"] = 6
        om.trigger_alert("cardio_zone", severity="WARNING")
        event = ctrl.receive_alert_trigger.call_args[0][0]
        assert "cardio_zone" in event.payload["description"]

    def test_alert_zone_id_matches(self):
        om, ctrl = _make_manager()
        om.zone_occupancy_counts["smart_machine_zone"] = 4
        om.trigger_alert("smart_machine_zone", severity="WARNING")
        event = ctrl.receive_alert_trigger.call_args[0][0]
        assert event.zone_id == "smart_machine_zone"


class TestRemoveMember:
    def test_remove_decrements_cycling_zoneount(self):
        om, _ = _make_manager()
        om.update_location_density("m1", "cardio_zone")
        om.update_location_density("m2", "cardio_zone")
        om.remove_member("m1")
        assert om.zone_occupancy_counts["cardio_zone"] == 1

    def test_remove_unknown_member_is_safe(self):
        om, _ = _make_manager()
        om.remove_member("not_a_member")  # should not raise

    def test_count_never_goes_below_zero(self):
        om, _ = _make_manager()
        om.zone_occupancy_counts["cardio_zone"] = 0
        om._member_locations["m1"] = "cardio_zone"
        om.remove_member("m1")
        assert om.zone_occupancy_counts["cardio_zone"] == 0


class TestGetSnapshot:
    def test_snapshot_reflects_current_state(self):
        om, _ = _make_manager()
        om.update_location_density("m1", "cardio_zone")
        om.update_location_density("m2", "smart_machine_zone")
        snap = om.get_snapshot()
        assert snap["cardio_zone"] == 1
        assert snap["smart_machine_zone"] == 1

    def test_snapshot_is_a_copy(self):
        om, _ = _make_manager()
        om.update_location_density("m1", "cardio_zone")
        snap = om.get_snapshot()
        snap["cardio_zone"] = 999
        assert om.zone_occupancy_counts["cardio_zone"] == 1
