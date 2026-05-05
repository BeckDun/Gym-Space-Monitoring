"""
Overcrowding Detection Demo
---------------------------
Flow (SAD section 7):
  WristbandDriver → SensorInterface → OccupancyManager → SystemController → DeviceDriver → Staff Tablet

Usage: python -m demos.overcrowding_demo
"""
from __future__ import annotations

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

from backend.controller.system_controller import SystemController
from backend.db.database_controller import DatabaseController
from backend.processing.occupancy_manager import OccupancyManager
from backend.sensor.device_driver import DeviceDriver
from backend.sensor.sensor_driver import WristbandDriver
from backend.sensor.sensor_interface import SensorInterface

ZONE_ID = "cardio_zone"  # threshold = 30 (from config)


def main() -> None:
    db = DatabaseController()
    device_driver = DeviceDriver()
    system_controller = SystemController(device_driver=device_driver, database_controller=db)

    sensor_interface = SensorInterface()
    occupancy_manager = OccupancyManager(system_controller=system_controller)

    print("\n=== Overcrowding Detection Demo ===\n")
    print(f"Zone threshold for {ZONE_ID}: {occupancy_manager.zone_occupancy_thresholds.get(ZONE_ID)} patrons\n")

    # Simulate 35 members entering cardio_zone (threshold is 30)
    for i in range(35):
        member_id = f"member_{i:03d}"
        driver = WristbandDriver(member_id=member_id, zone_id=ZONE_ID)
        raw = driver.read()
        event = sensor_interface.normalize_signal(raw)

        # Step 1: OccupancyManager.update_location_density (triggers verify_threshold internally)
        occupancy_manager.update_location_density(event.member_id, event.zone_id)

        count = occupancy_manager.zone_occupancy_counts.get(ZONE_ID, 0)
        print(f"  Member {i+1:02d} entered {ZONE_ID} — count: {count}")

    print(f"\n[OccupancyManager] Final counts: {occupancy_manager.get_snapshot()}")

    active = system_controller.get_active_alerts()
    print(f"\n[SystemController] Active alerts ({len(active)}):")
    for a in active:
        print(f"  [{a['severity']}] {a['description']}")


if __name__ == "__main__":
    main()
