# Gym Space Monitoring (GSM)

**Team T01** — CS 460 Software Engineering  
Beckett Dunlavy (manager), Aditya Chauhan, Christian Maestas, Oscar McCoy, Isaac Tapia

Real-time monitoring system for a private residential gym (~300–500 residents, ~6,000 sq ft). Detects falls, conflicts, overcrowding, and biometric anomalies. Surfaces alerts to staff tablets and logs usage data for management reports.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI 0.115 |
| Database | SQLite (default) / PostgreSQL 16 via Docker |
| ORM | SQLAlchemy 2.0 + aiosqlite / psycopg2-binary |
| AI/MLLM | Google Gemini API (`gemini-2.0-flash`) via `google-genai` |
| Frontend | Vanilla JS, HTML/CSS (no build step) |
| Real-time | WebSockets + Server-Sent Events (SSE) |
| Tests | pytest 8.2 + pytest-asyncio, httpx |

---

## Architecture

Event-driven, two pipelines:

- **Real-time alerting** — video/wristband data → MLLM/detection modules → System Controller → Staff Tablet (WebSocket push)
- **Observational** — passive logging → Database Controller → Usage Report Generator → Management Dashboard (REST)

---

## Repository Structure

```
├── backend/
│   ├── config.py           # env-based config (DATABASE_URL, GEMINI_API_KEY, thresholds)
│   ├── main.py             # FastAPI app, routes, WebSocket handlers
│   ├── sensor/             # sensor_interface.py, sensor_driver.py, device_driver.py
│   ├── processing/         # mllm_processor.py, fall_detection.py, conflict_detection.py,
│   │                       # occupancy_manager.py, biometric_analysis.py
│   ├── controller/         # system_controller.py
│   ├── db/                 # database_controller.py, models.py
│   ├── reporting/          # usage_report_generator.py
│   └── demos/              # demo_runner.py (SSE-based demo executor)
├── frontend/
│   ├── demos/              # Interactive demo page (SSE log viewer + DB state viewer)
│   ├── staff_tablet/       # Staff alert dashboard (WebSocket)
│   └── management_dashboard/ # Usage reports and analytics (REST)
├── demos/                  # CLI simulation scripts for each use case
├── database/
│   └── schema.sql          # PostgreSQL DDL (ORM auto-creates for SQLite)
├── tests/                  # pytest test suite
├── docker-compose.yml      # PostgreSQL 16 container
├── start.py                # One-command startup script
└── .env.example            # Environment variable template
```

---

## Configuration

All runtime settings are read from environment variables (`.env` file or shell exports). Copy `.env.example` to `.env` and fill in values.

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | _(empty)_ | Google Gemini API key. If blank, mock MLLM is used automatically. |
| `DATABASE_URL` | `sqlite:///./gsm.db` | SQLAlchemy database URL. See Database section below. |
| `USE_MOCK_MLLM` | `0` | Set to `1` to force mock MLLM output (skips real Gemini calls). |

**Thresholds** (set in `backend/config.py`):

| Setting | Value |
|---|---|
| `MLLM_MODEL` | `gemini-2.0-flash` |
| `FALL_CONFIDENCE_THRESHOLD` | `6.0` |
| `CONFLICT_CONFIDENCE_THRESHOLD` | `6.0` |
| Zone capacities | `zone_a=30, zone_b=25, zone_c=20, zone_d=20, entrance=10` |

---

## Database

The app supports two databases selected via `DATABASE_URL`:

### SQLite (default — no setup needed)
```
DATABASE_URL=sqlite:///./gsm.db
```
The ORM creates `gsm.db` automatically on first run. Best for local development.

### PostgreSQL 16 via Docker
```
DATABASE_URL=postgresql://postgres:password@localhost:5432/gsm
```
The Docker container is defined in `docker-compose.yml` and initializes the schema from `database/schema.sql` on first boot.

---

## Setup

### 1. Prerequisites

- Python 3.12+
- Docker Desktop (optional — needed only for PostgreSQL)

### 2. Python environment

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Environment variables

```bash
cp .env.example .env
# Edit .env — add your GEMINI_API_KEY (or leave blank to use mock MLLM)
```

### 4. Start the server

**Recommended — one-command startup (`start.py`):**

```bash
python start.py              # auto-detects Docker; falls back to SQLite
python start.py --sqlite     # force SQLite (skips Docker)
python start.py --postgres   # force PostgreSQL via Docker
python start.py --no-browser # don't open browser automatically
```

**Manual startup:**

```bash
uvicorn backend.main:app --reload
```

---

## Pages & API

| URL | Description |
|---|---|
| `http://127.0.0.1:8000/demos` | Interactive demo runner (default landing page) |
| `http://127.0.0.1:8000/staff` | Staff tablet — live alert dashboard |
| `http://127.0.0.1:8000/management` | Management dashboard — usage reports |
| `http://127.0.0.1:8000/docs` | FastAPI auto-generated API docs |
| `http://127.0.0.1:8000/health` | Health check |

### REST Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/alerts` | List active alerts |
| `POST` | `/api/resolve/{alert_id}` | Mark alert resolved |
| `GET` | `/api/report/{schedule}` | Generate usage report (`daily`/`weekly`/`monthly`) |
| `GET` | `/api/demos/stream/{demo_name}` | SSE stream for demo runner |
| `GET` | `/api/demos/db-state` | Full DB snapshot for demo viewer |
| `POST` | `/api/demos/reset` | Wipe demo data and re-seed members |

### WebSocket Endpoints

| Path | Description |
|---|---|
| `/ws/alerts` | Staff tablet — receives real-time alert pushes |
| `/ws/wristband/{member_id}` | Member wristband — receives haptic/visual warnings |

---

## Running Demos

**Via the web UI** (recommended): open `http://127.0.0.1:8000/demos` and click a demo button.

**Via CLI scripts:**

```bash
python -m demos.fall_detection_demo
python -m demos.abnormal_heart_rate_demo
python -m demos.overcrowding_demo
python -m demos.conflict_detection_demo
python -m demos.equipment_usage_demo
```

---

## Tests

```bash
pytest
```

Tests live in `tests/` and use `pytest-asyncio` (auto mode) with `httpx` for async HTTP client testing. The test suite mocks the MLLM and uses an in-memory SQLite database — no external services needed.

---

## Rollout Timeline

| Date | Milestone |
|---|---|
| Apr 25 | Data Store, Database Controller, System Controller, Staff Tablet |
| May 2 | Occupancy Manager, Management Dashboard |
| May 7 | Fall Detection, Conflict Detection (full MLLM pipeline) |
