from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, ForeignKey
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Member(Base):
    __tablename__ = "members"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    age = Column(Integer)
    bmi = Column(Float)
    activity_level = Column(String)           # "low" | "moderate" | "high"
    heart_rate_threshold_low = Column(Float, default=50.0)
    heart_rate_threshold_high = Column(Float, default=160.0)

    sessions = relationship("GymSession", back_populates="member")
    biometric_snapshots = relationship("BiometricSnapshot", back_populates="member")
    equipment_usages = relationship("EquipmentUsage", back_populates="member")
    alert_logs = relationship("AlertLog", back_populates="member")


class GymSession(Base):
    __tablename__ = "gym_sessions"

    id = Column(String, primary_key=True)
    member_id = Column(String, ForeignKey("members.id"), nullable=False)
    entry_time = Column(DateTime, default=datetime.utcnow)
    exit_time = Column(DateTime, nullable=True)
    zone_id = Column(String)

    member = relationship("Member", back_populates="sessions")


class AlertLog(Base):
    __tablename__ = "alert_logs"

    id = Column(String, primary_key=True)
    alert_id = Column(String, nullable=False, unique=True)
    severity = Column(String, nullable=False)  # "CRITICAL" | "WARNING" | "INFO"
    zone_id = Column(String)
    description = Column(String)
    member_id = Column(String, ForeignKey("members.id"), nullable=True)
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    member = relationship("Member", back_populates="alert_logs")


class EquipmentUsage(Base):
    __tablename__ = "equipment_usage"

    id = Column(String, primary_key=True)
    member_id = Column(String, ForeignKey("members.id"), nullable=False)
    machine_id = Column(String, nullable=False)
    zone_id = Column(String)
    reps = Column(Integer)
    resistance = Column(Float)
    started_at = Column(DateTime, default=datetime.utcnow)

    member = relationship("Member", back_populates="equipment_usages")


class BiometricSnapshot(Base):
    __tablename__ = "biometric_snapshots"

    id = Column(String, primary_key=True)
    member_id = Column(String, ForeignKey("members.id"), nullable=False)
    heart_rate = Column(Float)
    spo2 = Column(Float)
    zone_id = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

    member = relationship("Member", back_populates="biometric_snapshots")


class OccupancySnapshot(Base):
    __tablename__ = "occupancy_snapshots"

    id = Column(String, primary_key=True)
    zone_id = Column(String, nullable=False)
    count = Column(Integer, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
