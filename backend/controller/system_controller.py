from __future__ import annotations

import logging
from datetime import datetime

from backend.sensor.device_driver import Alert, DeviceDriver
from backend.sensor.sensor_interface import Event

logger = logging.getLogger(__name__)


class SystemController:
    """
    Central coordinator for the real-time alerting pipeline.

    SAD variables:
        activeAlerts — all live pending alerts requiring staff attention

    SAD methods:
        receiveAlertTrigger(Event) — primary sink for alert triggers from monitoring modules
        dispatchAlert(Alert)       — routes to DeviceDriver for hardware distribution
        logSystemEvent(Event)      — forwards to DatabaseController for archival
    """

    def __init__(self, device_driver: DeviceDriver, database_controller) -> None:
        self.active_alerts: list[Alert] = []          # SAD: activeAlerts
        self._device_driver = device_driver
        self._db = database_controller

    def receive_alert_trigger(self, event: Event) -> None:  # SAD: receiveAlertTrigger(Event)
        """
        Primary sink for all alert triggers from FallDetection, ConflictDetection,
        BiometricAnalysis, and OccupancyManager.
        Builds an Alert from the event and dispatches it.
        """
        severity = event.payload.get("severity", "INFO")
        description = event.payload.get("description", "")
        alert = Alert(
            severity=severity,
            zone_id=event.zone_id,
            description=description,
            member_id=event.member_id,
            timestamp=event.timestamp,
        )
        self.active_alerts.append(alert)
        logger.info(
            "Alert received [%s] zone=%s member=%s: %s",
            severity, event.zone_id, event.member_id, description,
        )
        self.dispatch_alert(alert)
        self.log_system_event(event)

    def dispatch_alert(self, alert: Alert) -> None:  # SAD: dispatchAlert(Alert)
        """
        Routes formatted alert notification to DeviceDriver.
        For biometric warnings, also pushes to the member's wristband.
        """
        self._device_driver.push_to_tablet(alert)

        # Biometric warnings go to both tablet AND the member's wristband (SAD Abnormal HR step 6)
        if alert.severity == "WARNING" and alert.member_id and "heart rate" in alert.description.lower():
            self._device_driver.push_to_wristband(
                alert.member_id,
                f"Heart rate alert: {alert.description}. Please reduce intensity.",
            )

    def log_system_event(self, event: Event) -> None:  # SAD: logSystemEvent(Event)
        """
        Forwards event data to DatabaseController for archival.
        Also used when staff resolves an alert (resolution feedback loop).
        """
        if event.type == "alert_resolution":
            alert_id = event.payload.get("alert_id")
            resolved_alert = next((a for a in self.active_alerts if a.alert_id == alert_id), None)
            if resolved_alert:
                resolved_alert.resolved = True
                self.active_alerts = [a for a in self.active_alerts if a.alert_id != alert_id]
                self._db.log_alerts(resolved_alert)
                logger.info("Alert resolved and archived: %s", alert_id)
            return

        # For all other event types, find the matching active alert and log it
        matching = [a for a in self.active_alerts if a.zone_id == event.zone_id and not a.resolved]
        if matching:
            self._db.log_alerts(matching[-1])

    def resolve_alert(self, alert_id: str) -> bool:
        """
        Called by the API endpoint when staff marks an alert resolved.
        Triggers log_system_event with a resolution event (SAD Fall Detection step 8).
        Returns True if the alert was found and resolved.
        """
        resolution_event = Event(
            type="alert_resolution",
            payload={"alert_id": alert_id},
            zone_id="",
            member_id=None,
            timestamp=datetime.utcnow(),
        )
        found = any(a.alert_id == alert_id for a in self.active_alerts)
        if found:
            self.log_system_event(resolution_event)
        return found

    def get_active_alerts(self) -> list[dict]:
        return [a.to_dict() for a in self.active_alerts]
