from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class Alert:
    severity: str          # "CRITICAL" | "WARNING" | "INFO"
    zone_id: str
    description: str
    member_id: str | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    alert_id: str = field(default_factory=lambda: str(uuid4()))
    resolved: bool = False

    def to_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "severity": self.severity,
            "zone_id": self.zone_id,
            "description": self.description,
            "member_id": self.member_id,
            "timestamp": self.timestamp.isoformat(),
            "resolved": self.resolved,
        }


class DeviceDriver:
    """
    Translates software alerts into output device commands.

    SAD variables:
        activeStaffTablets  — WebSocket connections to staff tablet interfaces
        activeWristbands    — WebSocket connections to member wristband screens
    """

    def __init__(self) -> None:
        self.active_staff_tablets: dict[str, Any] = {}   # SAD: activeStaffTablets
        self.active_wristbands: dict[str, Any] = {}      # SAD: activeWristbands

    def register_tablet(self, device_id: str, websocket: Any) -> None:
        self.active_staff_tablets[device_id] = websocket
        logger.info("Staff tablet registered: %s", device_id)

    def unregister_tablet(self, device_id: str) -> None:
        self.active_staff_tablets.pop(device_id, None)

    def register_wristband(self, member_id: str, websocket: Any) -> None:
        self.active_wristbands[member_id] = websocket

    def unregister_wristband(self, member_id: str) -> None:
        self.active_wristbands.pop(member_id, None)

    def push_to_tablet(self, alert: Alert) -> None:  # SAD: pushToTablet(Alert)
        """Broadcast alert JSON to all connected staff tablets."""
        payload = json.dumps(alert.to_dict())
        if not self.active_staff_tablets:
            logger.warning("[TABLET] No tablets connected — alert: %s", payload)
            return
        for device_id, ws in list(self.active_staff_tablets.items()):
            try:
                asyncio.get_event_loop().create_task(ws.send_text(payload))
                logger.info("[TABLET %s] Sent %s alert: %s", device_id, alert.severity, alert.description)
            except Exception as exc:
                logger.error("[TABLET %s] Send failed: %s", device_id, exc)
                self.active_staff_tablets.pop(device_id, None)

    def push_to_wristband(self, member_id: str, warning: str) -> None:  # SAD: pushToWristband(MemberID, Warning)
        """Send haptic + text warning to a specific member's wristband."""
        ws = self.active_wristbands.get(member_id)
        if ws is None:
            logger.warning("[WRISTBAND %s] Not connected — warning: %s", member_id, warning)
            return
        payload = json.dumps({"member_id": member_id, "warning": warning, "timestamp": datetime.utcnow().isoformat()})
        try:
            asyncio.get_event_loop().create_task(ws.send_text(payload))
            logger.info("[WRISTBAND %s] Sent warning: %s", member_id, warning)
        except Exception as exc:
            logger.error("[WRISTBAND %s] Send failed: %s", member_id, exc)
            self.active_wristbands.pop(member_id, None)
