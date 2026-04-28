"""
Fall Detection Demo
-------------------
Flow (SAD section 7):
  CameraDriver → SensorInterface → MLLMProcessor → FallDetection → SystemController → DeviceDriver → Staff Tablet

Runs a single video analysis pass and prints the resulting alert.
Usage: python -m demos.fall_detection_demo
"""
from __future__ import annotations

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

from backend.controller.system_controller import SystemController
from backend.db.database_controller import DatabaseController
from backend.processing.fall_detection import FALL_PROMPT, FallDetection
from backend.processing.mllm_processor import MLLMProcessor
from backend.sensor.device_driver import DeviceDriver
from backend.sensor.sensor_driver import CameraDriver
from backend.sensor.sensor_interface import SensorInterface

VIDEO_PATH = "Man_Falling_in_Gym_Video.mp4"
ZONE_ID = "zone_a"


def main() -> None:
    db = DatabaseController()
    device_driver = DeviceDriver()
    system_controller = SystemController(device_driver=device_driver, database_controller=db)

    sensor_interface = SensorInterface()
    camera_driver = CameraDriver(video_path=VIDEO_PATH, zone_id=ZONE_ID)
    mllm_processor = MLLMProcessor()
    fall_detection = FallDetection(system_controller=system_controller)

    print("\n=== Fall Detection Demo ===\n")

    # Step 1-2: Camera → Sensor Interface
    raw_signal = camera_driver.read()
    event = sensor_interface.normalize_signal(raw_signal)
    print(f"[SensorInterface] Normalized video event: zone={event.zone_id}, {len(event.payload['video_bytes'])/1024:.1f} KB")

    # Step 3: MLLM Processor analyzes video
    print("[MLLMProcessor] Sending to Gemini...")
    mllm_output = mllm_processor.analyze(event, FALL_PROMPT)
    print(f"[MLLMProcessor] Response: {mllm_output}")

    # Step 4-5: Fall Detection evaluates and triggers alert
    fall_detection.analyze_mllm_output(mllm_output, zone_id=ZONE_ID)

    # Step 6-7: Show what was dispatched
    active = system_controller.get_active_alerts()
    if active:
        print(f"\n[SystemController] Active alerts ({len(active)}):")
        for a in active:
            print(f"  [{a['severity']}] {a['description'][:120]}")
    else:
        print("\n[SystemController] No alerts triggered (fall score below threshold).")


if __name__ == "__main__":
    main()
