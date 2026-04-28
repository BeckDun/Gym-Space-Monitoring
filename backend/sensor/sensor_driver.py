from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Iterator

from backend.sensor.sensor_interface import RawSignal


class SensorDriver(ABC):
    """Base class for all sensor drivers (physical or simulated)."""

    def __init__(self, source: str, zone_id: str) -> None:
        self.source = source
        self.zone_id = zone_id

    @abstractmethod
    def read(self) -> RawSignal:
        """Return the next single signal."""

    @abstractmethod
    def stream(self) -> Iterator[RawSignal]:
        """Yield signals continuously."""


class CameraDriver(SensorDriver):
    """
    Reads a video file as raw bytes and yields it as a RawSignal.
    Matches the gemini_example.py pattern exactly:
        video_bytes = open(video_file_name, 'rb').read()
    """

    def __init__(self, video_path: str, zone_id: str, interval_seconds: float = 5.0) -> None:
        super().__init__(source="camera", zone_id=zone_id)
        self.video_path = video_path
        self.interval_seconds = interval_seconds

    def read(self) -> RawSignal:
        video_bytes = open(self.video_path, "rb").read()
        return RawSignal(
            source=self.source,
            data=video_bytes,
            metadata={"zone_id": self.zone_id, "timestamp": datetime.utcnow()},
        )

    def stream(self) -> Iterator[RawSignal]:
        while True:
            yield self.read()
            time.sleep(self.interval_seconds)


class WristbandDriver(SensorDriver):
    """
    Simulates a wristband transmitting biometric and location data.
    Real implementation would read from BLE/WiFi receiver.
    Each call yields both heart_rate and position in one payload.
    """

    def __init__(
        self,
        member_id: str,
        zone_id: str,
        heart_rate: float | None = None,
        interval_seconds: float = 1.0,
    ) -> None:
        super().__init__(source="wristband", zone_id=zone_id)
        self.member_id = member_id
        self._heart_rate = heart_rate
        self.interval_seconds = interval_seconds

    def read(self) -> RawSignal:
        hr = self._heart_rate if self._heart_rate is not None else random.uniform(60, 100)
        return RawSignal(
            source=self.source,
            data={
                "member_id": self.member_id,
                "heart_rate": round(hr, 1),
                "spo2": round(random.uniform(95, 100), 1),
                "zone_id": self.zone_id,
                "x": round(random.uniform(0, 100), 2),
                "y": round(random.uniform(0, 60), 2),
            },
            metadata={"zone_id": self.zone_id, "member_id": self.member_id, "timestamp": datetime.utcnow()},
        )

    def stream(self) -> Iterator[RawSignal]:
        while True:
            yield self.read()
            time.sleep(self.interval_seconds)


class EquipmentDriver(SensorDriver):
    """
    Simulates a smart strength machine emitting rep/resistance data.
    Real implementation would read from machine NFC reader + embedded sensors.
    """

    def __init__(
        self,
        machine_id: str,
        zone_id: str,
        member_id: str,
        reps: int | None = None,
        resistance: float | None = None,
        interval_seconds: float = 2.0,
    ) -> None:
        super().__init__(source="equipment", zone_id=zone_id)
        self.machine_id = machine_id
        self.member_id = member_id
        self._reps = reps
        self._resistance = resistance
        self.interval_seconds = interval_seconds

    def read(self) -> RawSignal:
        return RawSignal(
            source=self.source,
            data={
                "machine_id": self.machine_id,
                "member_id": self.member_id,
                "reps": self._reps if self._reps is not None else random.randint(8, 15),
                "resistance": self._resistance if self._resistance is not None else random.uniform(20, 120),
                "state": "active",
            },
            metadata={"zone_id": self.zone_id, "member_id": self.member_id, "timestamp": datetime.utcnow()},
        )

    def stream(self) -> Iterator[RawSignal]:
        while True:
            yield self.read()
            time.sleep(self.interval_seconds)


class EntranceDriver(SensorDriver):
    """
    Simulates a member tapping in or out at the gym entrance NFC reader.
    """

    def __init__(self, member_id: str, action: str = "entry") -> None:
        super().__init__(source="entrance", zone_id="entrance")
        self.member_id = member_id
        self.action = action  # "entry" | "exit"

    def read(self) -> RawSignal:
        return RawSignal(
            source=self.source,
            data={"member_id": self.member_id, "action": self.action},
            metadata={"zone_id": self.zone_id, "member_id": self.member_id, "timestamp": datetime.utcnow()},
        )

    def stream(self) -> Iterator[RawSignal]:
        yield self.read()
