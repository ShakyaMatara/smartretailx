import asyncio
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from consumer import start_consumer
from hub import hub
from shared.events import DELIVERY_UPDATED, publish
from shared.logging_config import configure_logging

logger = configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_consumer(asyncio.get_running_loop())
    yield


app = FastAPI(
    title="SmartRetailX Notification Service",
    description="Real-time event push over WebSocket.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health/live", tags=["Health"])
def liveness():
    return {"status": "alive", "service": "notification-service"}


@app.get("/health/ready", tags=["Health"])
def readiness():
    return {
        "status": "ready",
        "service": "notification-service",
        "connected_clients": hub.count(),
    }


@app.get("/", include_in_schema=False)
def demo_page():
    """Serves the live event dashboard."""
    return FileResponse("static/index.html")


@app.websocket("/ws/events")
async def events_socket(websocket: WebSocket):
    """
    Persistent connection for real-time event delivery.

    Production note: this endpoint is unauthenticated for the
    demonstration. A production deployment would validate a JWT during
    the handshake and scope each connection to that user's own events.
    """
    await hub.connect(websocket)
    logger.info(f"Client connected ({hub.count()} total)")

    try:
        while True:
            # Keeps the connection open; also absorbs client pings.
            await websocket.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect(websocket)
        logger.info(f"Client disconnected ({hub.count()} remaining)")


@app.post("/api/v1/notifications/delivery/{order_id}", tags=["Notifications"])
def publish_delivery_update(order_id: str, status: str = "IN_TRANSIT"):
    """
    Publish a delivery tracking update.

    Simulates the courier webhook that would drive real delivery
    tracking, satisfying the delivery-tracking requirement of Task 4.
    """
    publish(DELIVERY_UPDATED, {
        "order_id": order_id, "delivery_status": status,
    }, str(uuid.uuid4()))
    return {"order_id": order_id, "delivery_status": status}