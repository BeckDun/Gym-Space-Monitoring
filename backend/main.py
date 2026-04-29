from __future__ import annotations

import json
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend.controller.system_controller import SystemController
from backend.db.database_controller import DatabaseController
from backend.sensor.device_driver import DeviceDriver

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# --- Component wiring ---
db = DatabaseController()
device_driver = DeviceDriver()
system_controller = SystemController(device_driver=device_driver, database_controller=db)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    db.seed_members()
    logger.info("GSM backend started.")
    yield
    logger.info("GSM backend shutting down.")


app = FastAPI(title="Gym Space Monitoring", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Page routes (served before static mount) ─────────────────────────────────

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/demos")


@app.get("/demos", include_in_schema=False)
def demos_page():
    return FileResponse("frontend/demos/index.html")


@app.get("/staff", include_in_schema=False)
def staff_page():
    return FileResponse("frontend/staff_tablet/index.html")


@app.get("/management", include_in_schema=False)
def management_page():
    return FileResponse("frontend/management_dashboard/index.html")


# ── Core API ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "active_alerts": len(system_controller.active_alerts)}


@app.get("/api/alerts")
def get_alerts():
    return {"alerts": system_controller.get_active_alerts()}


@app.post("/api/resolve/{alert_id}")
def resolve_alert(alert_id: str):
    """Staff marks an alert as resolved. SAD Fall Detection step 8."""
    found = system_controller.resolve_alert(alert_id)
    if not found:
        return {"success": False, "message": f"Alert {alert_id} not found or already resolved."}
    return {"success": True, "alert_id": alert_id}


@app.get("/api/report/{schedule}")
def get_report(schedule: str):
    from backend.reporting.usage_report_generator import UsageReportGenerator
    gen = UsageReportGenerator(database_controller=db)
    try:
        return gen.generate(schedule)
    except ValueError as e:
        return {"error": str(e)}


# ── Demos API ─────────────────────────────────────────────────────────────────

@app.get("/api/demos/stream/{demo_name}", include_in_schema=False)
async def stream_demo(demo_name: str):
    """SSE endpoint — streams step-by-step log entries for the demos page."""
    from backend.demos import demo_runner

    async def event_generator():
        async for entry in demo_runner.run(demo_name):
            yield f"data: {json.dumps(entry)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/demos/db-state")
def demo_db_state():
    """Return a full snapshot of the database for the demos page viewer."""
    return db.get_full_state()


@app.post("/api/demos/reset")
def reset_demo_db():
    """Wipe all demo data and re-seed members."""
    from backend.db.models import AlertLog, BiometricSnapshot, EquipmentUsage, OccupancySnapshot
    with db._session() as session:
        session.query(AlertLog).delete()
        session.query(BiometricSnapshot).delete()
        session.query(EquipmentUsage).delete()
        session.query(OccupancySnapshot).delete()
        session.commit()
    # Clear in-memory active alerts
    system_controller.active_alerts.clear()
    db.seed_members()
    return {"success": True, "message": "Database reset and re-seeded."}


# ── WebSockets ────────────────────────────────────────────────────────────────

@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    """Staff tablet subscribes here to receive real-time alert pushes."""
    await websocket.accept()
    device_id = str(uuid.uuid4())
    device_driver.register_tablet(device_id, websocket)
    logger.info("Staff tablet connected: %s", device_id)

    for alert_dict in system_controller.get_active_alerts():
        await websocket.send_text(json.dumps(alert_dict))

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        device_driver.unregister_tablet(device_id)
        logger.info("Staff tablet disconnected: %s", device_id)


@app.websocket("/ws/wristband/{member_id}")
async def websocket_wristband(websocket: WebSocket, member_id: str):
    """Member wristband subscribes here to receive private haptic/visual warnings."""
    await websocket.accept()
    device_driver.register_wristband(member_id, websocket)
    logger.info("Wristband connected: member %s", member_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        device_driver.unregister_wristband(member_id)
        logger.info("Wristband disconnected: member %s", member_id)


# ── Static files (must come after all API/page routes) ───────────────────────

app.mount("/static", StaticFiles(directory="frontend"), name="static")
app.mount("/video", StaticFiles(directory="."), name="video_files")
