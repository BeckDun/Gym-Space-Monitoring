from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from backend.sensor.sensor_interface import Event

logger = logging.getLogger(__name__)


@dataclass
class HealthProfile:
    member_id: str
    age: int
    bmi: float
    activity_level: str                    # "low" | "moderate" | "high"
    heart_rate_threshold_low: float        # SAD: heartRateThresholdLow
    heart_rate_threshold_high: float       # SAD: heartRateThresholdHigh


class BiometricStatus(Enum):
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"


class BiometricAnalysis:
    """
    Processes wristband biometric data and compares against member health profiles.

    SAD variables:
        heartRateThresholdLow  — lower safety limit from member's health profile
        heartRateThresholdHigh — upper safety limit from member's health profile
        currentProfile         — active member's stored data retrieved from Data Store
    """

    def __init__(self, system_controller) -> None:
        self._system_controller = system_controller
        self.heart_rate_threshold_low: float = 50.0     # SAD: heartRateThresholdLow (default)
        self.heart_rate_threshold_high: float = 160.0   # SAD: heartRateThresholdHigh (default)
        self.current_profile: HealthProfile | None = None  # SAD: currentProfile

    def evaluate_heart_rate(  # SAD: evaluateHeartRate(float, HealthProfile)
        self,
        current_heart_rate: float,
        profile: HealthProfile,
    ) -> BiometricStatus:
        """Assess live heart rate readings against the member's stored personal thresholds."""
        self.current_profile = profile
        self.heart_rate_threshold_low = profile.heart_rate_threshold_low
        self.heart_rate_threshold_high = profile.heart_rate_threshold_high

        if current_heart_rate < profile.heart_rate_threshold_low or current_heart_rate > profile.heart_rate_threshold_high:
            return BiometricStatus.WARNING

        return BiometricStatus.NORMAL

    def trigger_alert(  # SAD: triggerAlert(BiometricStatus, MemberID, ZoneID)
        self,
        status: BiometricStatus,
        member_id: str,
        zone_id: str,
        current_heart_rate: float | None = None,
    ) -> None:
        """Issue a Warning Alert to the System Controller when biometric abnormalities detected."""
        if status == BiometricStatus.NORMAL:
            return

        hr_info = f" (HR: {current_heart_rate:.0f} bpm)" if current_heart_rate is not None else ""
        description = (
            f"Abnormal heart rate detected for member {member_id} in {zone_id}{hr_info}. "
            f"Thresholds: {self.heart_rate_threshold_low:.0f}–{self.heart_rate_threshold_high:.0f} bpm."
        )
        event = Event(
            type="alert",
            payload={"severity": "WARNING", "description": description},
            zone_id=zone_id,
            member_id=member_id,
            timestamp=datetime.utcnow(),
        )
        # SystemController.dispatch_alert() will push to BOTH tablet AND wristband (SAD HR step 6)
        self._system_controller.receive_alert_trigger(event)

    def process_event(self, event: Event, profile: HealthProfile) -> None:
        """Convenience method: evaluate a biometric Event and trigger alert if needed."""
        heart_rate = event.payload.get("heart_rate")
        if heart_rate is None:
            return
        status = self.evaluate_heart_rate(heart_rate, profile)
        if status != BiometricStatus.NORMAL:
            self.trigger_alert(status, event.member_id, event.zone_id, heart_rate)
