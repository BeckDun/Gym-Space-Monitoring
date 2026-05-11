from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.config import DATABASE_URL
from backend.db.models import AlertLog, Base, BiometricSnapshot, EquipmentUsage, GymSession, Member, OccupancySnapshot
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

    def get_full_state(self) -> dict:
        """Return a snapshot of all tables for the demos database viewer."""
        with self._session() as session:
            members = [
                {"id": r.id, "name": r.name, "age": r.age, "activity_level": r.activity_level,
                 "hr_low": r.heart_rate_threshold_low, "hr_high": r.heart_rate_threshold_high}
                for r in session.query(Member).all()
            ]
            alerts = [
                {"alert_id": r.alert_id, "severity": r.severity, "zone_id": r.zone_id,
                 "description": r.description, "member_id": r.member_id,
                 "resolved": r.resolved, "created_at": r.created_at.isoformat() if r.created_at else None}
                for r in session.query(AlertLog).order_by(AlertLog.created_at.desc()).limit(20).all()
            ]
            equipment = [
                {"member_id": r.member_id, "machine_id": r.machine_id, "zone_id": r.zone_id,
                 "reps": r.reps, "resistance": r.resistance,
                 "started_at": r.started_at.isoformat() if r.started_at else None}
                for r in session.query(EquipmentUsage).order_by(EquipmentUsage.started_at.desc()).limit(20).all()
            ]
            biometric = [
                {"member_id": r.member_id, "heart_rate": r.heart_rate, "spo2": r.spo2,
                 "zone_id": r.zone_id,
                 "timestamp": r.timestamp.isoformat() if r.timestamp else None}
                for r in session.query(BiometricSnapshot).order_by(BiometricSnapshot.timestamp.desc()).limit(20).all()
            ]
            occupancy = [
                {"zone_id": r.zone_id, "count": r.count,
                 "timestamp": r.timestamp.isoformat() if r.timestamp else None}
                for r in session.query(OccupancySnapshot).order_by(OccupancySnapshot.timestamp.desc()).limit(20).all()
            ]
            gym_sessions = [
                {"id": r.id, "member_id": r.member_id,
                 "entry_time": r.entry_time.isoformat() if r.entry_time else None,
                 "exit_time": r.exit_time.isoformat() if r.exit_time else None,
                 "zone_id": r.zone_id}
                for r in session.query(GymSession).order_by(GymSession.entry_time.desc()).limit(20).all()
            ]
        return {
            "members": members,
            "alert_logs": alerts,
            "equipment_usage": equipment,
            "biometric_snapshots": biometric,
            "occupancy_snapshots": occupancy,
            "gym_sessions": gym_sessions,
        }

    def seed_members(self) -> None:
        """Insert demo seed members if not already present."""
        from backend.db.models import Member
        SEED = [
            {"id": "member_001", "name": "Alice Johnson", "age": 32, "bmi": 22.5,
             "activity_level": "moderate", "heart_rate_threshold_low": 55.0, "heart_rate_threshold_high": 165.0},
            {"id": "member_002", "name": "Bob Smith", "age": 45, "bmi": 27.8,
             "activity_level": "low", "heart_rate_threshold_low": 50.0, "heart_rate_threshold_high": 140.0},
            {"id": "member_003", "name": "Carol Davis", "age": 28, "bmi": 21.1,
             "activity_level": "high", "heart_rate_threshold_low": 60.0, "heart_rate_threshold_high": 185.0},
            {"id": "member_004", "name": "David Lee", "age": 35, "bmi": 24.3,
             "activity_level": "moderate", "heart_rate_threshold_low": 52.0, "heart_rate_threshold_high": 160.0},
            {"id": "member_005", "name": "Emma Wilson", "age": 29, "bmi": 20.8,
             "activity_level": "high", "heart_rate_threshold_low": 58.0, "heart_rate_threshold_high": 180.0},
            {"id": "member_006", "name": "Frank Martinez", "age": 41, "bmi": 26.0,
             "activity_level": "low", "heart_rate_threshold_low": 48.0, "heart_rate_threshold_high": 145.0},
            {"id": "member_007", "name": "Grace Kim", "age": 26, "bmi": 21.9,
             "activity_level": "high", "heart_rate_threshold_low": 55.0, "heart_rate_threshold_high": 175.0},
        ]
        with self._session() as session:
            for m in SEED:
                if not session.query(Member).filter_by(id=m["id"]).first():
                    session.add(Member(**m))
            session.commit()
        logger.info("Seed members ensured.")

    def log_session(self, member_id: str, action: str) -> dict:
        """Create a GymSession entry or close an open one. Returns session info."""
        with self._session() as session:
            if action == "entry":
                record = GymSession(
                    id=str(uuid4()),
                    member_id=member_id,
                    entry_time=datetime.utcnow(),
                    exit_time=None,
                    zone_id="entrance",
                )
                session.add(record)
                session.commit()
                logger.info("GymSession created: member %s tapped in", member_id)
                return {
                    "member_id": member_id,
                    "action": action,
                    "session_id": record.id,
                    "entry_time": record.entry_time.isoformat(),
                }
            else:  # exit
                open_session = (
                    session.query(GymSession)
                    .filter_by(member_id=member_id, exit_time=None)
                    .order_by(GymSession.entry_time.desc())
                    .first()
                )
                if open_session:
                    open_session.exit_time = datetime.utcnow()
                    session.commit()
                    logger.info("GymSession closed: member %s tapped out", member_id)
                    return {
                        "member_id": member_id,
                        "action": action,
                        "session_id": open_session.id,
                        "entry_time": open_session.entry_time.isoformat(),
                    }
                return {"member_id": member_id, "action": action, "session_id": None, "entry_time": None}

    def get_members_with_status(self) -> list:
        """Return all members with in_gym boolean and entry_time from open GymSession."""
        with self._session() as session:
            members = session.query(Member).all()
            result = []
            for m in members:
                open_session = (
                    session.query(GymSession)
                    .filter_by(member_id=m.id, exit_time=None)
                    .order_by(GymSession.entry_time.desc())
                    .first()
                )
                result.append({
                    "id": m.id,
                    "name": m.name,
                    "age": m.age,
                    "activity_level": m.activity_level,
                    "hr_low": m.heart_rate_threshold_low,
                    "hr_high": m.heart_rate_threshold_high,
                    "in_gym": open_session is not None,
                    "entry_time": open_session.entry_time.isoformat() if open_session else None,
                })
            return result

    def add_member(self) -> dict:
        """Generate and insert a new member with a complete random health profile."""
        import random
        from backend.db.models import Member

        FIRST_NAMES = [
            "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Quinn",
            "Avery", "Harper", "Logan", "Blake", "Drew", "Sage", "Reese",
            "Skyler", "Dakota", "Jamie", "Kendall", "Rowan", "Finley",
            "Cameron", "Emery", "Hayden", "Parker", "Peyton", "Sawyer",
            "Spencer", "Sydney", "Tatum", "Zion",
        ]
        LAST_NAMES = [
            "Anderson", "Brown", "Chen", "Diaz", "Evans", "Foster", "Garcia",
            "Hayes", "Inoue", "Jackson", "Kumar", "Lopez", "Miller", "Nguyen",
            "Ortiz", "Patel", "Quinn", "Rivera", "Santos", "Thompson",
            "Ueda", "Vargas", "Williams", "Xu", "Young", "Zhang",
        ]
        ACTIVITY_LEVELS = ["low", "moderate", "high"]

        with self._session() as session:
            # Find the next unique member number
            existing = session.query(Member).all()
            existing_nums = []
            for m in existing:
                try:
                    existing_nums.append(int(m.id.split("_")[-1]))
                except (ValueError, IndexError):
                    pass
            next_num = max(existing_nums, default=0) + 1
            member_id = f"member_{next_num:03d}"

            name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            age = random.randint(18, 65)
            bmi = round(random.uniform(18.5, 32.0), 1)
            activity_level = random.choice(ACTIVITY_LEVELS)

            # Derive HR thresholds from age (max HR ≈ 220 - age)
            max_hr = 220 - age
            if activity_level == "high":
                hr_low = round(max_hr * 0.30, 1)
                hr_high = round(max_hr * 0.95, 1)
            elif activity_level == "moderate":
                hr_low = round(max_hr * 0.28, 1)
                hr_high = round(max_hr * 0.85, 1)
            else:  # low
                hr_low = round(max_hr * 0.25, 1)
                hr_high = round(max_hr * 0.75, 1)

            member = Member(
                id=member_id, name=name, age=age, bmi=bmi,
                activity_level=activity_level,
                heart_rate_threshold_low=hr_low,
                heart_rate_threshold_high=hr_high,
            )
            session.add(member)
            session.commit()
            logger.info("New member added: %s (%s)", member_id, name)

        return {
            "id": member_id, "name": name, "age": age, "bmi": bmi,
            "activity_level": activity_level,
            "hr_low": hr_low, "hr_high": hr_high,
        }
