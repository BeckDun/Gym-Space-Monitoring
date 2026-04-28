"""
Equipment Usage Reporting Demo
-------------------------------
Flow (SAD section 7):
  EquipmentDriver → SensorInterface → DatabaseController → Data Store
  → UsageReportGenerator.generate() → Management Dashboard

Usage: python -m demos.equipment_usage_demo
"""
from __future__ import annotations

import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

from backend.db.database_controller import DatabaseController, EquipmentData
from backend.reporting.usage_report_generator import UsageReportGenerator
from backend.sensor.sensor_driver import EquipmentDriver
from backend.sensor.sensor_interface import SensorInterface

MACHINES = [
    ("machine_press_01", "zone_a"),
    ("machine_row_01", "zone_b"),
    ("machine_press_01", "zone_a"),
    ("machine_curl_01", "zone_c"),
    ("machine_row_01", "zone_b"),
    ("machine_press_01", "zone_a"),
]


def main() -> None:
    db = DatabaseController()
    db.init_db()

    sensor_interface = SensorInterface()
    report_generator = UsageReportGenerator(database_controller=db)

    print("\n=== Equipment Usage Reporting Demo ===\n")

    # Steps 1-2: Equipment tap-in → Sensor Interface → DatabaseController
    for i, (machine_id, zone_id) in enumerate(MACHINES):
        member_id = f"member_{(i % 3) + 1:03d}"
        driver = EquipmentDriver(machine_id=machine_id, zone_id=zone_id, member_id=member_id, reps=12, resistance=80.0)

        raw = driver.read()
        event = sensor_interface.normalize_signal(raw)

        equipment_data = EquipmentData(
            member_id=event.member_id,
            machine_id=event.payload["machine_id"],
            zone_id=event.zone_id,
            reps=event.payload["reps"],
            resistance=event.payload["resistance"],
        )
        db.log_weight_lifting(equipment_data)
        print(f"  Logged: {member_id} on {machine_id} — {equipment_data.reps} reps @ {equipment_data.resistance:.0f}kg")

    # Steps 4-6: Usage Report Generator compiles report
    print("\n[UsageReportGenerator] Generating daily report...\n")
    report = report_generator.generate("daily")

    print(f"  Period: {report['period_start']} → {report['period_end']}")
    print(f"  Equipment sessions: {report['equipment_summary']['total_sessions']}")
    print(f"  Usage ranking:")
    for entry in report["equipment_summary"]["usage_ranking"]:
        print(f"    {entry['machine_id']}: {entry['sessions']} sessions, {entry['total_reps']} total reps")
    print(f"  Alert summary: {report['alert_summary']}")


if __name__ == "__main__":
    main()
