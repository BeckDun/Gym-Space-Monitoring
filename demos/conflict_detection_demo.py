"""
Member-to-Member Conflict Demo
-------------------------------
Flow (SAD section 7):
  CameraDriver → SensorInterface → MLLMProcessor → ConflictDetection → SystemController → DeviceDriver → Staff Tablet

Usage: python -m demos.conflict_detection_demo
"""
from __future__ import annotations

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

from backend.controller.system_controller import SystemController
from backend.db.database_controller import DatabaseController
from backend.processing.conflict_detection import CONFLICT_PROMPT, ConflictDetection
from backend.processing.fall_detection import FALL_PROMPT, FallDetection
from backend.processing.mllm_processor import MLLMProcessor
from backend.sensor.device_driver import DeviceDriver
from backend.sensor.sensor_driver import CameraDriver
from backend.sensor.sensor_interface import SensorInterface

VIDEO_PATH = "Man_Falling_in_Gym_Video.mp4"
ZONE_ID = "zone_c"


def main() -> None:
    db = DatabaseController()
    device_driver = DeviceDriver()
    system_controller = SystemController(device_driver=device_driver, database_controller=db)

    sensor_interface = SensorInterface()
    camera_driver = CameraDriver(video_path=VIDEO_PATH, zone_id=ZONE_ID)
    mllm_processor = MLLMProcessor()

    # Both detectors share the same MLLM output for the same video event
    fall_detection = FallDetection(system_controller=system_controller)
    conflict_detection = ConflictDetection(system_controller=system_controller)

    print("\n=== Conflict Detection Demo ===\n")

    # Steps 1-2: D Driver → Sensor Interface
    raw_signal = camera_driver.read()
    event = sensor_interface.normalize_signal(raw_signal)
    print(f"[SensorInterface] Video event: zone={event.zone_id}")

    # Step 2: MLLM Processor — run both prompts on the same video
    print("[MLLMProcessor] Analyzing for falls...")
    fall_output = mllm_processor.analyze(event, FALL_PROMPT)
    print(f"  Fall response: {fall_output}")

    print("[MLLMProcessor] Analyzing for conflicts...")
    conflict_output = mllm_processor.analyze(event, CONFLICT_PROMPT)
    print(f"  Conflict response: {conflict_output}")

    # Steps 3-4: Both detectors independently evaluate
    fall_detection.analyze_mllm_output(fall_output, zone_id=ZONE_ID)
    conflict_detection.analyze_mllm_output(conflict_output, zone_id=ZONE_ID)

    # Step 5: Results
    active = system_controller.get_active_alerts()
    print(f"\n[SystemController] Active alerts ({len(active)}):")
    for a in active:
        print(f"  [{a['severity']}] {a['description'][:120]}")
    if not active:
        print("  (none — scores below thresholds)")


if __name__ == "__main__":
    main()
