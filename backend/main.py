from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

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


@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    """Staff tablet subscribes here to receive real-time alert pushes."""
    await websocket.accept()
    device_id = str(uuid.uuid4())
    device_driver.register_tablet(device_id, websocket)
    logger.info("Staff tablet connected: %s", device_id)

    # Send current active alerts on connect
    for alert_dict in system_controller.get_active_alerts():
        import json
        await websocket.send_text(json.dumps(alert_dict))

    try:
        while True:
            await websocket.receive_text()  # keep connection alive; tablet sends ack pings
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
