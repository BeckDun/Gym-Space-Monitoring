# Gym Space Monitoring (GSM)

**Team T01** — CS 460 Software Engineering  
Beckett Dunlavy (manager), Aditya Chauhan, Christian Maestas, Oscar McCoy, Isaac Tapia

Real-time monitoring system for a private residential gym (~300–500 residents, ~6,000 sq ft). Detects falls, conflicts, overcrowding, and biometric anomalies. Surfaces alerts to staff tablets and logs usage data for management reports.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI |
| Database | PostgreSQL (TimescaleDB) + SQLAlchemy |
| AI/MLLM | Google Gemini API |
| Frontend | Vanilla JS, HTML/CSS |
| Real-time | WebSockets |
| Simulations | Python scripts (mock sensor payloads) |

---

## Architecture

Event-driven, two pipelines:

- **Real-time alerting** — video/wristband data → MLLM/detection modules → System Controller → Staff Tablet
- **Observational** — passive logging → Database Controller → Usage Report Generator → Management Dashboard

---

## Repository Structure

```
├── backend/
│   ├── sensor/         # sensor_interface.py, sensor_driver.py, device_driver.py
│   ├── processing/     # mllm_processor.py, fall_detection.py, conflict_detection.py,
│   │                   # occupancy_manager.py, biometric_analysis.py
│   ├── controller/     # system_controller.py
│   ├── db/             # database_controller.py, models.py
│   ├── reporting/      # usage_report_generator.py
│   └── main.py
├── frontend/
│   ├── staff_tablet/           # Staff alert dashboard
│   └── management_dashboard/   # Usage reports and analytics
├── demos/              # Simulation scripts for each use case
├── database/
│   └── schema.sql
└── docs/               # SAD, SRS, RDD
```

---

## Setup

### Brew Installs
```bash
which brew && brew info postgresql
brew install postgresql
```
### Backend
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# add Gemini API key and DB credentials to config.py or .env
uvicorn backend.main:app --reload
```

### Frontend
Open `http://127.0.0.1:8000/staff` or `http://127.0.0.1:8000/static/management_dashboard/index.html` or `http://127.0.0.1:8000/demos`in a browser.

### Run Demos
```bash
python3 -m demos.fall_detection_demo
python3 -m demos.abnormal_heart_rate_demo
python3 -m demos.overcrowding_demo
python3 -m demos.conflict_detection_demo
python3 -m demos.equipment_usage_demo
```

---

## Rollout Timeline

| Date | Milestone |
|---|---|
| Apr 25 | Data Store, Database Controller, System Controller, Staff Tablet |
| May 2 | Occupancy Manager, Management Dashboard |
| May 7 | Fall Detection, Conflict Detection (full MLLM pipeline) |
