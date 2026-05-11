"""Unit tests for SensorInterface.normalize_signal routing (SAD §3 Sensor Interface)."""
from __future__ import annotations

import pytest
from datetime import datetime

from backend.sensor.sensor_interface import RawSignal, SensorInterface, Event


@pytest.fixture
def si():
    return SensorInterface()


def _meta(zone="cardio_zone", member=None):
    return {"zone_id": zone, "member_id": member, "timestamp": datetime.utcnow()}


class TestNormalizeCamera:
    def test_camera_produces_video_event(self, si):
        raw = RawSignal(source="camera", data=b"\x00\x01\x02", metadata=_meta("smart_machine_zone"))
        event = si.normalize_signal(raw)
        assert event.type == "video"
        assert event.zone_id == "smart_machine_zone"

    def test_camera_payload_has_video_bytes(self, si):
        raw = RawSignal(source="camera", data=b"abc", metadata=_meta())
        event = si.normalize_signal(raw)
        assert event.payload["video_bytes"] == b"abc"
        assert event.payload["mime_type"] == "video/mp4"

    def test_camera_stores_current_signal(self, si):
        raw = RawSignal(source="camera", data=b"x", metadata=_meta())
        si.normalize_signal(raw)
        assert si.current_signal is raw


class TestNormalizeWristband:
    def test_biometric_event_when_heart_rate_present(self, si):
        raw = RawSignal(
            source="wristband",
            data={"heart_rate": 78.0, "spo2": 98.0, "member_id": "m1", "zone_id": "cardio_zone"},
            metadata=_meta(member="m1"),
        )
        event = si.normalize_signal(raw)
        assert event.type == "biometric"
        assert event.payload["heart_rate"] == 78.0
        assert event.member_id == "m1"

    def test_location_event_when_only_position(self, si):
        raw = RawSignal(
            source="wristband",
            data={"x": 10.5, "y": 20.3, "zone_id": "cycling_zone", "member_id": "m2"},
            metadata=_meta("cycling_zone", "m2"),
        )
        event = si.normalize_signal(raw)
        assert event.type == "location"
        assert event.payload["x"] == 10.5

    def test_biometric_takes_priority_over_position(self, si):
        raw = RawSignal(
            source="wristband",
            data={"heart_rate": 85.0, "x": 5.0, "y": 10.0, "zone_id": "cardio_zone", "member_id": "m3"},
            metadata=_meta(),
        )
        event = si.normalize_signal(raw)
        assert event.type == "biometric"


class TestNormalizeEquipment:
    def test_equipment_event(self, si):
        raw = RawSignal(
            source="equipment",
            data={"machine_id": "press_01", "member_id": "m1", "reps": 10, "resistance": 50.0, "state": "active"},
            metadata=_meta("smart_machine_zone", "m1"),
        )
        event = si.normalize_signal(raw)
        assert event.type == "equipment"
        assert event.payload["reps"] == 10
        assert event.payload["machine_id"] == "press_01"

    def test_equipment_zone_from_metadata(self, si):
        raw = RawSignal(
            source="equipment",
            data={"machine_id": "x", "member_id": "m1", "reps": 5, "resistance": 20.0, "state": "active"},
            metadata=_meta("functional_zone"),
        )
        event = si.normalize_signal(raw)
        assert event.zone_id == "functional_zone"


class TestNormalizeEntrance:
    def test_session_event_entry(self, si):
        raw = RawSignal(
            source="entrance",
            data={"member_id": "m5", "action": "entry"},
            metadata=_meta("entrance", "m5"),
        )
        event = si.normalize_signal(raw)
        assert event.type == "session"
        assert event.payload["action"] == "entry"

    def test_session_event_exit(self, si):
        raw = RawSignal(
            source="entrance",
            data={"member_id": "m5", "action": "exit"},
            metadata=_meta("entrance", "m5"),
        )
        event = si.normalize_signal(raw)
        assert event.payload["action"] == "exit"


class TestNormalizeUnknown:
    def test_unknown_source_raises(self, si):
        raw = RawSignal(source="unknown_device", data={}, metadata=_meta())
        with pytest.raises(ValueError, match="Unknown signal source"):
            si.normalize_signal(raw)
