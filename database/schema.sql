-- GSM Data Store Schema
-- Matches backend/db/models.py SQLAlchemy ORM definitions

CREATE TABLE IF NOT EXISTS members (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    age INTEGER,
    bmi FLOAT,
    activity_level VARCHAR,
    heart_rate_threshold_low FLOAT DEFAULT 50.0,
    heart_rate_threshold_high FLOAT DEFAULT 160.0
);

CREATE TABLE IF NOT EXISTS gym_sessions (
    id VARCHAR PRIMARY KEY,
    member_id VARCHAR NOT NULL REFERENCES members(id),
    entry_time TIMESTAMP DEFAULT NOW(),
    exit_time TIMESTAMP,
    zone_id VARCHAR
);

CREATE TABLE IF NOT EXISTS alert_logs (
    id VARCHAR PRIMARY KEY,
    alert_id VARCHAR NOT NULL UNIQUE,
    severity VARCHAR NOT NULL,
    zone_id VARCHAR,
    description TEXT,
    member_id VARCHAR REFERENCES members(id),
    resolved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS equipment_usage (
    id VARCHAR PRIMARY KEY,
    member_id VARCHAR NOT NULL REFERENCES members(id),
    machine_id VARCHAR NOT NULL,
    zone_id VARCHAR,
    reps INTEGER,
    resistance FLOAT,
    started_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS biometric_snapshots (
    id VARCHAR PRIMARY KEY,
    member_id VARCHAR NOT NULL REFERENCES members(id),
    heart_rate FLOAT,
    spo2 FLOAT,
    zone_id VARCHAR,
    timestamp TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS occupancy_snapshots (
    id VARCHAR PRIMARY KEY,
    zone_id VARCHAR NOT NULL,
    count INTEGER NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW()
);

-- TimescaleDB hypertables for time-series performance (run after enabling TimescaleDB extension)
-- SELECT create_hypertable('biometric_snapshots', 'timestamp', if_not_exists => TRUE);
-- SELECT create_hypertable('occupancy_snapshots', 'timestamp', if_not_exists => TRUE);
