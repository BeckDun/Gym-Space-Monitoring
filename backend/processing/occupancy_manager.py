from __future__ import annotations

import logging
from datetime import datetime

from backend.config import ZONE_THRESHOLDS
from backend.sensor.sensor_interface import Event

logger = logging.getLogger(__name__)


class OccupancyManager:
    """
    Maintains real-time zone occupancy counts from wristband location signals.

    SAD variables:
        zoneOccupancyCounts     — real-time tally of patrons per zone
        zoneOccupancyThresholds — safety capacity limits per zone
    """

    def __init__(self, system_controller) -> None:
        self._system_controller = system_controller
        self.zone_occupancy_counts: dict[str, int] = {}            # SAD: zoneOccupancyCounts
        self.zone_occupancy_thresholds: dict[str, int] = dict(ZONE_THRESHOLDS)  # SAD: zoneOccupancyThresholds
        self._member_locations: dict[str, str] = {}  # member_id → zone_id (for move tracking)

    def update_location_density(self, member_id: str, zone_id: str) -> None:  # SAD: updateLocationDensity
        """Update internal tracking of patron distribution from location signals."""
        previous_zone = self._member_locations.get(member_id)

        if previous_zone and previous_zone != zone_id:
            self.zone_occupancy_counts[previous_zone] = max(
                0, self.zone_occupancy_counts.get(previous_zone, 0) - 1
            )

        self._member_locations[member_id] = zone_id
        self.zone_occupancy_counts[zone_id] = self.zone_occupancy_counts.get(zone_id, 0) + 1

        logger.debug("Zone %s count: %d", zone_id, self.zone_occupancy_counts[zone_id])
        self.verify_threshold(zone_id)

    def verify_threshold(self, zone_id: str) -> None:  # SAD: verifyThreshold(ZoneID)
        """Evaluate current zone occupancy against the maximum allowable density."""
        count = self.zone_occupancy_counts.get(zone_id, 0)
        threshold = self.zone_occupancy_thresholds.get(zone_id, 30)

        if count >= threshold:
            logger.warning("Zone %s OVERCROWDED: %d/%d", zone_id, count, threshold)
            self.trigger_alert(zone_id, severity="WARNING")
        elif count >= int(threshold * 0.8):
            logger.info("Zone %s approaching capacity: %d/%d", zone_id, count, threshold)
            self.trigger_alert(zone_id, severity="INFO")

    def trigger_alert(self, zone_id: str, severity: str = "WARNING") -> None:  # SAD: triggerAlert(ZoneID)
        """Notify the System Controller of overcrowding events."""
        count = self.zone_occupancy_counts.get(zone_id, 0)
        threshold = self.zone_occupancy_thresholds.get(zone_id, 30)
        description = (
            f"Zone {zone_id} {'overcrowded' if severity == 'WARNING' else 'approaching capacity'}: "
            f"{count}/{threshold} patrons."
        )
        event = Event(
            type="alert",
            payload={"severity": severity, "description": description},
            zone_id=zone_id,
            member_id=None,
            timestamp=datetime.utcnow(),
        )
        self._system_controller.receive_alert_trigger(event)

    def remove_member(self, member_id: str) -> None:
        """Decrement zone count when a member exits (session close)."""
        zone_id = self._member_locations.pop(member_id, None)
        if zone_id:
            self.zone_occupancy_counts[zone_id] = max(0, self.zone_occupancy_counts.get(zone_id, 0) - 1)

    def get_snapshot(self) -> dict[str, int]:
        return dict(self.zone_occupancy_counts)
