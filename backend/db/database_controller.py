from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.config import DATABASE_URL
from backend.db.models import AlertLog, Base, BiometricSnapshot, EquipmentUsage, OccupancySnapshot
from backend.sensor.device_driver import Alert

logger = logging.getLogger(__name__)


@dataclass
class EquipmentData:
    member_id: str
    machine_id: str
    zone_id: str
    reps: int
    resistance: float
    started_at: datetime = None

    def __post_init__(self):
        if self.started_at is None:
            self.started_at = datetime.utcnow()


@dataclass
class BiometricData:
    member_id: str
    heart_rate: float
    spo2: float
    zone_id: str
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


@dataclass
class OccupancyData:
    zone_id: str
    count: int
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


@dataclass
class QueryRequest:
    report_type: str        # "occupancy" | "equipment" | "alerts" | "biometric"
    start_time: datetime
    end_time: datetime
    zone_id: str | None = None
    member_id: str | None = None


class DatabaseController:
    """Manages all interactions with the Data Store."""

    def __init__(self) -> None:
        self.engine = create_engine(DATABASE_URL)
        self._SessionLocal = sessionmaker(bind=self.engine)
        self.data_store_connection: Session | None = None  # SAD: dataStoreConnection

    def init_db(self) -> None:
        Base.metadata.create_all(self.engine)
        logger.info("Database schema initialized.")

    def _session(self) -> Session:
        return self._SessionLocal()

    def log_weight_lifting(self, data: EquipmentData) -> None:  # SAD: logWeightLifting(EquipmentData)
        """Store repetition and resistance data from smart machines."""
        with self._session() as session:
            record = EquipmentUsage(
                id=str(uuid4()),
                member_id=data.member_id,
                machine_id=data.machine_id,
                zone_id=data.zone_id,
                reps=data.reps,
                resistance=data.resistance,
                started_at=data.started_at,
            )
            session.add(record)
            session.commit()
            logger.info("Logged equipment usage: %s reps @ %.1f for member %s", data.reps, data.resistance, data.member_id)

    def log_bio_occupancy(self, biometric: BiometricData, occupancy: OccupancyData) -> None:  # SAD: logBioOccupancy
        """Log wristband telemetry and zone density snapshots."""
        with self._session() as session:
            bio_record = BiometricSnapshot(
                id=str(uuid4()),
                member_id=biometric.member_id,
                heart_rate=biometric.heart_rate,
                spo2=biometric.spo2,
                zone_id=biometric.zone_id,
                timestamp=biometric.timestamp,
            )
            occ_record = OccupancySnapshot(
                id=str(uuid4()),
                zone_id=occupancy.zone_id,
                count=occupancy.count,
                timestamp=occupancy.timestamp,
            )
            session.add(bio_record)
            session.add(occ_record)
            session.commit()

    def log_alerts(self, alert: Alert) -> None:  # SAD: logAlerts(Alert)
        """Archive system alerts to build historical safety datasets."""
        with self._session() as session:
            record = AlertLog(
                id=str(uuid4()),
                alert_id=alert.alert_id,
                severity=alert.severity,
                zone_id=alert.zone_id,
                description=alert.description,
                member_id=alert.member_id,
                resolved=alert.resolved,
                created_at=alert.timestamp,
            )
            existing = session.query(AlertLog).filter_by(alert_id=alert.alert_id).first()
            if existing:
                existing.resolved = alert.resolved
            else:
                session.add(record)
            session.commit()
            logger.info("Alert logged: [%s] %s (resolved=%s)", alert.severity, alert.description, alert.resolved)

    def handle_report_query(self, query: QueryRequest) -> dict:  # SAD: handleReportQuery(QueryRequest)
        """Retrieve data subsets requested by the Usage Report Generator."""
        with self._session() as session:
            if query.report_type == "equipment":
                rows = session.query(EquipmentUsage).filter(
                    EquipmentUsage.started_at >= query.start_time,
                    EquipmentUsage.started_at <= query.end_time,
                ).all()
                return {
                    "report_type": "equipment",
                    "records": [
                        {"machine_id": r.machine_id, "member_id": r.member_id, "reps": r.reps, "resistance": r.resistance, "started_at": r.started_at.isoformat()}
                        for r in rows
                    ],
                }

            if query.report_type == "occupancy":
                rows = session.query(OccupancySnapshot).filter(
                    OccupancySnapshot.timestamp >= query.start_time,
                    OccupancySnapshot.timestamp <= query.end_time,
                ).all()
                return {
                    "report_type": "occupancy",
                    "records": [
                        {"zone_id": r.zone_id, "count": r.count, "timestamp": r.timestamp.isoformat()}
                        for r in rows
                    ],
                }

            if query.report_type == "alerts":
                rows = session.query(AlertLog).filter(
                    AlertLog.created_at >= query.start_time,
                    AlertLog.created_at <= query.end_time,
                ).all()
                return {
                    "report_type": "alerts",
                    "records": [
                        {"alert_id": r.alert_id, "severity": r.severity, "zone_id": r.zone_id, "description": r.description, "resolved": r.resolved}
                        for r in rows
                    ],
                }

            if query.report_type == "biometric":
                q = session.query(BiometricSnapshot).filter(
                    BiometricSnapshot.timestamp >= query.start_time,
                    BiometricSnapshot.timestamp <= query.end_time,
                )
                if query.member_id:
                    q = q.filter(BiometricSnapshot.member_id == query.member_id)
                rows = q.all()
                return {
                    "report_type": "biometric",
                    "records": [
                        {"member_id": r.member_id, "heart_rate": r.heart_rate, "spo2": r.spo2, "zone_id": r.zone_id, "timestamp": r.timestamp.isoformat()}
                        for r in rows
                    ],
                }

            raise ValueError(f"Unknown report_type: {query.report_type!r}")
