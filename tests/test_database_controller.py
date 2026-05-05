"""Integration tests for DatabaseController using SQLite in-memory (SAD §3 Database Controller)."""
from __future__ import annotations

import os
import pytest
from datetime import datetime
from unittest.mock import patch

# Use SQLite in-memory for all DB tests
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture
def db():
    with patch("backend.config.DATABASE_URL", "sqlite:///:memory:"):
        from backend.db.database_controller import DatabaseController
        controller = DatabaseController.__new__(DatabaseController)
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from backend.db.models import Base
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        controller.engine = engine
        controller._SessionLocal = sessionmaker(bind=engine)
        controller.data_store_connection = None
        return controller


@pytest.fixture
def seed_member(db):
    """Insert a member row required by FK constraints."""
    from sqlalchemy.orm import sessionmaker
    from backend.db.models import Member
    with db._session() as session:
        session.add(Member(
            id="m1", name="Test User", age=30, bmi=22.0,
            activity_level="moderate",
            heart_rate_threshold_low=50.0,
            heart_rate_threshold_high=160.0,
        ))
        session.commit()


class TestLogAlerts:
    def test_log_alert_inserts_row(self, db):
        from backend.sensor.device_driver import Alert
        alert = Alert(severity="CRITICAL", zone_id="cardio_zone", description="Test fall", member_id=None)
        db.log_alerts(alert)

        from backend.db.models import AlertLog
        with db._session() as session:
            row = session.query(AlertLog).filter_by(alert_id=alert.alert_id).first()
        assert row is not None
        assert row.severity == "CRITICAL"

    def test_log_alert_updates_existing_row(self, db):
        from backend.sensor.device_driver import Alert
        from backend.db.models import AlertLog
        alert = Alert(severity="WARNING", zone_id="smart_machine_zone", description="Overcrowded", member_id=None)
        db.log_alerts(alert)
        alert.resolved = True
        db.log_alerts(alert)

        with db._session() as session:
            rows = session.query(AlertLog).filter_by(alert_id=alert.alert_id).all()
        assert len(rows) == 1
        assert rows[0].resolved is True


class TestLogWeightLifting:
    def test_log_weight_lifting_inserts_row(self, db, seed_member):
        from backend.db.database_controller import EquipmentData
        from backend.db.models import EquipmentUsage
        data = EquipmentData(member_id="m1", machine_id="press_01", zone_id="smart_machine_zone", reps=12, resistance=60.0)
        db.log_weight_lifting(data)

        with db._session() as session:
            rows = session.query(EquipmentUsage).filter_by(member_id="m1").all()
        assert len(rows) == 1
        assert rows[0].reps == 12
        assert rows[0].resistance == 60.0


class TestLogBioOccupancy:
    def test_log_bio_occupancy_inserts_two_rows(self, db, seed_member):
        from backend.db.database_controller import BiometricData, OccupancyData
        from backend.db.models import BiometricSnapshot, OccupancySnapshot
        bio = BiometricData(member_id="m1", heart_rate=78.0, spo2=98.0, zone_id="cardio_zone")
        occ = OccupancyData(zone_id="cardio_zone", count=5)
        db.log_bio_occupancy(bio, occ)

        with db._session() as session:
            bio_row = session.query(BiometricSnapshot).filter_by(member_id="m1").first()
            occ_row = session.query(OccupancySnapshot).filter_by(zone_id="cardio_zone").first()
        assert bio_row.heart_rate == 78.0
        assert occ_row.count == 5


class TestHandleReportQuery:
    def test_equipment_report_returns_records(self, db, seed_member):
        from backend.db.database_controller import EquipmentData, QueryRequest
        db.log_weight_lifting(EquipmentData(member_id="m1", machine_id="squat_01", zone_id="cardio_zone", reps=8, resistance=80.0))
        result = db.handle_report_query(QueryRequest(
            report_type="equipment",
            start_time=datetime(2000, 1, 1),
            end_time=datetime(2099, 1, 1),
        ))
        assert result["report_type"] == "equipment"
        assert len(result["records"]) == 1

    def test_occupancy_report_returns_records(self, db, seed_member):
        from backend.db.database_controller import BiometricData, OccupancyData, QueryRequest
        db.log_bio_occupancy(
            BiometricData(member_id="m1", heart_rate=90.0, spo2=97.0, zone_id="cardio_zone"),
            OccupancyData(zone_id="cardio_zone", count=10),
        )
        result = db.handle_report_query(QueryRequest(
            report_type="occupancy",
            start_time=datetime(2000, 1, 1),
            end_time=datetime(2099, 1, 1),
        ))
        assert result["report_type"] == "occupancy"
        assert len(result["records"]) >= 1

    def test_alerts_report_returns_records(self, db):
        from backend.sensor.device_driver import Alert
        from backend.db.database_controller import QueryRequest
        alert = Alert(severity="INFO", zone_id="cardio_zone", description="Test")
        db.log_alerts(alert)
        result = db.handle_report_query(QueryRequest(
            report_type="alerts",
            start_time=datetime(2000, 1, 1),
            end_time=datetime(2099, 1, 1),
        ))
        assert len(result["records"]) >= 1

    def test_unknown_report_type_raises(self, db):
        from backend.db.database_controller import QueryRequest
        with pytest.raises(ValueError, match="Unknown report_type"):
            db.handle_report_query(QueryRequest(
                report_type="unknown",
                start_time=datetime(2000, 1, 1),
                end_time=datetime(2099, 1, 1),
            ))
