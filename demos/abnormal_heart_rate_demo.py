"""
Abnormal Heart Rate Demo
------------------------
Flow (SAD section 7):
  WristbandDriver → SensorInterface → BiometricAnalysis → SystemController → DeviceDriver → Tablet + Wristband

Usage: python -m demos.abnormal_heart_rate_demo
"""
from __future__ import annotations

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

from backend.controller.system_controller import SystemController
from backend.db.database_controller import DatabaseController
from backend.processing.biometric_analysis import BiometricAnalysis, HealthProfile
from backend.sensor.device_driver import DeviceDriver
from backend.sensor.sensor_driver import WristbandDriver
from backend.sensor.sensor_interface import SensorInterface

MEMBER_ID = "member_001"
ZONE_ID = "smart_machine_zone"


def main() -> None:
    db = DatabaseController()
    device_driver = DeviceDriver()
    system_controller = SystemController(device_driver=device_driver, database_controller=db)

    sensor_interface = SensorInterface()
    biometric_analysis = BiometricAnalysis(system_controller=system_controller)

    profile = HealthProfile(
        member_id=MEMBER_ID,
        age=45,
        bmi=27.5,
        activity_level="moderate",
        heart_rate_threshold_low=55.0,
        heart_rate_threshold_high=150.0,
    )

    print("\n=== Abnormal Heart Rate Demo ===\n")
    print(f"Member profile: HR thresholds {profile.heart_rate_threshold_low:.0f}–{profile.heart_rate_threshold_high:.0f} bpm\n")

    # Simulate normal reading, then abnormal
    for heart_rate, label in [(80.0, "normal"), (185.0, "HIGH"), (40.0, "LOW")]:
        wristband_driver = WristbandDriver(member_id=MEMBER_ID, zone_id=ZONE_ID, heart_rate=heart_rate)

        # Step 1-2: S Driver → Sensor Interface
        raw_signal = wristband_driver.read()
        event = sensor_interface.normalize_signal(raw_signal)
        print(f"[SensorInterface] Biometric event: HR={event.payload['heart_rate']} bpm ({label})")

        # Step 3: BiometricAnalysis evaluates
        biometric_analysis.process_event(event, profile)

    # Step 5-6: Show dispatched alerts
    active = system_controller.get_active_alerts()
    print(f"\n[SystemController] Active alerts ({len(active)}):")
    for a in active:
        print(f"  [{a['severity']}] member={a['member_id']} — {a['description'][:100]}")
    if not active:
        print("  (none)")


if __name__ == "__main__":
    main()
