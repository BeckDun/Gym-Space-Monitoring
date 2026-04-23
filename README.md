# Gym Space Monitoring (GSM)

**Team T01** — CS 460 Software Engineering
Beckett Dunlavy (manager), Aditya Chauhan, Christian Maestas, Oscar McCoy, Isaac Tapia

---

## What It Is

A real-time monitoring system for a private residential gym (~300–500 residents, ~6,000 sq ft). The system detects falls, conflicts, overcrowding, and biometric anomalies, and surfaces alerts to staff tablets. It also logs usage data for management reports.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI |
| Database | PostgreSQL (TimescaleDB) + SQLAlchemy |
| AI/MLLM | Google Gemini API |
| Frontend | React 18, Vite, Tailwind CSS |
| Real-time | WebSockets |
| Simulations | Python scripts (mock sensor payloads) |

---

## Architecture

The system follows an **event-driven architecture** with two pipelines:

- **Real-time alerting** — video/wristband data → MLLM/detection modules → System Controller → Staff Tablet
- **Observational** — passive logging → Database Controller → Usage Report Generator → Management Dashboard

See `docs/` for the full SAD, SRS, and RDD.

---

## Repository Structure

```
gsm-system/
├── backend/                    # Python/FastAPI core
│   └── app/
│       ├── api/                # sensor_interface.py, device_driver.py
│       ├── core/               # system_controller.py, config.py
│       ├── db/                 # database_controller.py, models.py
│       └── services/           # occupancy_manager, mllm_processor, detection, report_generator
├── frontend/                   # React/Vite/Tailwind
│   └── src/
│       ├── components/         # Shared UI components
│       ├── views/              # StaffTablet.jsx, ManagementDash.jsx
│       └── services/           # websocketClient.js, apiClient.js
├── simulations/                # Mock sensor payloads (Phase 1 hardware replacement)
│   ├── d_driver/               # video_mock.py
│   └── s_driver/               # biometric_mock.py, occupancy_mock.py
└── docs/                       # SAD, SRS, RDD
```

---

## Setup

### Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # add Gemini API key and DB credentials
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Simulations
```bash
python simulations/s_driver/occupancy_mock.py
python simulations/d_driver/video_mock.py
```

---

## Rollout Timeline

| Date | Milestone |
|---|---|
| Apr 25 | Data Store, Database Controller, System Controller, Staff Tablet |
| May 2 | Occupancy Manager, Management Dashboard |
| May 7 | Fall Detection, Conflict Detection (full MLLM pipeline) |
