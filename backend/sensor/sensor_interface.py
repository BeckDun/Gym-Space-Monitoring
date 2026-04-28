from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RawSignal:
    source: str          # "camera" | "wristband" | "equipment" | "entrance"
    data: bytes | dict
    metadata: dict = field(default_factory=dict)


@dataclass
class Event:
    type: str            # "video" | "biometric" | "location" | "equipment" | "session"
    payload: dict
    zone_id: str
    member_id: str | None
    timestamp: datetime = field(default_factory=datetime.utcnow)


class SensorInterface:
    """Abstraction layer that normalizes raw hardware signals into standardized Events."""

    def __init__(self) -> None:
        self.current_signal: RawSignal | None = None  # SAD: currentSignal

    def normalize_signal(self, raw: RawSignal) -> Event:  # SAD: normalizeSignal(RawSignal)
        self.current_signal = raw
        zone_id = raw.metadata.get("zone_id", "unknown")
        member_id = raw.metadata.get("member_id")
        timestamp = raw.metadata.get("timestamp", datetime.utcnow())

        if raw.source == "camera":
            return Event(
                type="video",
                payload={"video_bytes": raw.data, "mime_type": "video/mp4"},
                zone_id=zone_id,
                member_id=member_id,
                timestamp=timestamp,
            )

        if raw.source == "wristband":
            data: dict = raw.data  # type: ignore[assignment]
            # Location signal if positional keys present alongside biometric
            has_position = "x" in data or "y" in data or "zone_id" in data
            has_biometric = "heart_rate" in data

            if has_biometric:
                biometric_event = Event(
                    type="biometric",
                    payload={
                        "heart_rate": data.get("heart_rate"),
                        "spo2": data.get("spo2"),
                    },
                    zone_id=data.get("zone_id", zone_id),
                    member_id=data.get("member_id", member_id),
                    timestamp=timestamp,
                )
                return biometric_event

            if has_position:
                return Event(
                    type="location",
                    payload={"x": data.get("x"), "y": data.get("y")},
                    zone_id=data.get("zone_id", zone_id),
                    member_id=data.get("member_id", member_id),
                    timestamp=timestamp,
                )

        if raw.source == "equipment":
            data = raw.data  # type: ignore[assignment]
            return Event(
                type="equipment",
                payload={
                    "reps": data.get("reps"),
                    "resistance": data.get("resistance"),
                    "state": data.get("state"),
                    "machine_id": data.get("machine_id"),
                },
                zone_id=zone_id,
                member_id=data.get("member_id", member_id),
                timestamp=timestamp,
            )

        if raw.source == "entrance":
            data = raw.data  # type: ignore[assignment]
            return Event(
                type="session",
                payload={"action": data.get("action")},  # "entry" | "exit"
                zone_id=zone_id,
                member_id=data.get("member_id", member_id),
                timestamp=timestamp,
            )

        raise ValueError(f"Unknown signal source: {raw.source!r}")
