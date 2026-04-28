from __future__ import annotations

import logging
import re
from datetime import datetime

from backend.config import CONFLICT_CONFIDENCE_THRESHOLD
from backend.sensor.sensor_interface import Event

logger = logging.getLogger(__name__)

CONFLICT_PROMPT = (
    "Analyze this gym footage for member conflict. "
    "Is there any aggressive or threatening physical behavior between patrons? "
    "Respond ONLY in this exact format — Conflict: <1-10>, Confidence: <1-10>"
)


class ConflictDetection:
    """
    Monitors MLLM output to detect member-to-member conflicts.

    SAD variables:
        mllmTextOutput      — latest structured event description from MLLM Processor
        conflictConfidence  — minimum threshold to confirm an aggressive interaction
    """

    def __init__(self, system_controller) -> None:
        self._system_controller = system_controller
        self.mllm_text_output: str = ""                              # SAD: mllmTextOutput
        self.conflict_confidence: float = CONFLICT_CONFIDENCE_THRESHOLD  # SAD: conflictConfidence

    def analyze_mllm_output(self, mllm_text_output: str, zone_id: str) -> None:  # SAD: analyzeMLLMOutput
        """
        Parse MLLM response and evaluate against conflictConfidence threshold.
        SAD Incident Detection Diagram:
          score >= conflictConfidence → CRITICAL alert
          4 <= score < conflictConfidence → WARNING (inconclusive)
          score < 4 → no alert
        """
        self.mllm_text_output = mllm_text_output
        score = self._parse_score(mllm_text_output, key="Conflict")

        logger.info("Conflict score: %.1f (threshold=%.1f, zone=%s)", score, self.conflict_confidence, zone_id)

        if score >= self.conflict_confidence:
            self.trigger_alert("CRITICAL", zone_id)
        elif score >= 4.0:
            self.trigger_alert("WARNING", zone_id)

    def trigger_alert(self, severity: str, zone_id: str) -> None:  # SAD: triggerAlert(AlertSeverity, ZoneID)
        """Dispatch confirmed conflict metadata to the System Controller."""
        description = (
            f"Conflict detected in {zone_id} (score {self._parse_score(self.mllm_text_output, 'Conflict'):.1f}/10). "
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
        match = re.search(rf"{re.escape(key)}:\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
        if match:
            return float(match.group(1))
        logger.warning("Could not parse '%s' score from: %r", key, text)
        return 0.0
