from __future__ import annotations

import logging
import re
from datetime import datetime

from backend.config import FALL_CONFIDENCE_THRESHOLD
from backend.sensor.sensor_interface import Event

logger = logging.getLogger(__name__)

FALL_PROMPT = """\
You are a gym safety monitoring system. Analyze this gym security footage.

A FALL is when a person collapses or drops to the floor involuntarily AND does NOT \
get back up on their own within the clip. Tripping, stumbling, or falling and then \
immediately recovering does NOT count as a fall.

Only score high if the person goes down and remains on the ground.

Reply with EXACTLY two lines and nothing else. Use a single integer on each line:
Fall: <integer>
Confidence: <integer>

Scale: 1 = definitely not a fall (or person recovered), 10 = definite unrecovered fall.

Correct example:
Fall: 8
Confidence: 9\
"""


class FallDetection:
    """
    Monitors MLLM output to detect member falls.

    SAD variables:
        mllmTextOutput  — latest structured event description from MLLM Processor
        fallConfidence  — minimum threshold to validate a fall event
    """

    def __init__(self, system_controller) -> None:
        self._system_controller = system_controller
        self.mllm_text_output: str = ""                   # SAD: mllmTextOutput
        self.fall_confidence: float = FALL_CONFIDENCE_THRESHOLD  # SAD: fallConfidence

    def analyze_mllm_output(self, mllm_text_output: str, zone_id: str) -> None:  # SAD: analyzeMLLMOutput
        """
        Parse MLLM response and evaluate against fallConfidence threshold.
        SAD Incident Detection Diagram:
          score >= fallConfidence  → CRITICAL alert
          4 <= score < fallConfidence → WARNING (inconclusive)
          score < 4               → no alert
        """
        self.mllm_text_output = mllm_text_output
        score = self._parse_score(mllm_text_output, key="Fall")

        logger.info("Fall score: %.1f (threshold=%.1f, zone=%s)", score, self.fall_confidence, zone_id)

        if score >= self.fall_confidence:
            self.trigger_alert("CRITICAL", zone_id)
        elif score >= 4.0:
            self.trigger_alert("WARNING", zone_id)

    def trigger_alert(self, severity: str, zone_id: str) -> None:  # SAD: triggerAlert(AlertSeverity, ZoneID)
        """Pass high-priority fall event and location data to the System Controller."""
        description = (
            f"Fall detected in {zone_id} (score {self._parse_score(self.mllm_text_output, 'Fall'):.1f}/10). "
            f"MLLM output: {self.mllm_text_output}"
        )
        event = Event(
            type="alert",
            payload={"severity": severity, "description": description},
            zone_id=zone_id,
            member_id=None,
            timestamp=datetime.utcnow(),
        )
        self._system_controller.receive_alert_trigger(event)

    @staticmethod
    def _parse_score(text: str, key: str) -> float:
        """
        Extract numeric score from MLLM response text.
        Handles both single values ('Fall: 8') and ranges ('Fall: 7-9'),
        taking the higher end of a range so edge cases aren't under-counted.
        """
        # Range format: "Fall: 7-9" → take upper bound (9)
        range_match = re.search(
            rf"{re.escape(key)}:\s*(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)",
            text, re.IGNORECASE,
        )
        if range_match:
            return float(range_match.group(2))

        # Single value: "Fall: 8"
        match = re.search(rf"{re.escape(key)}:\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
        if match:
            return float(match.group(1))

        logger.warning("Could not parse '%s' score from: %r", key, text)
        return 0.0
