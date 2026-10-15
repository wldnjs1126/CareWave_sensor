import asyncio

from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from aggregation.sensor_aggregator import aggregator
from api.schemas import RadarFrameBatchIn, RadarFrameIn
from api.control import router as control_router
from api.live import live_manager
from database.connection import engine


KST = ZoneInfo("Asia/Seoul")

BASE_DIR = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

VISUALIZATION_DIR = (
    BASE_DIR
    / "visualization"
)


def _build_live_payload(
    frames: list[RadarFrameIn],
) -> dict | None:
    frame_ids = [
        frame.frame_id
        for frame in frames
        if frame.frame_id is not None
    ]

    if not frame_ids:
        return None

    latest_frame_id = max(frame_ids)

    latest_frames = [
        frame
        for frame in frames
        if frame.frame_id == latest_frame_id
    ]

    targets_by_id: dict[int, dict] = {}

    for frame in latest_frames:
        if (
            frame.target_id is None
            or frame.x is None
            or frame.y is None
        ):
            continue

        targets_by_id[frame.target_id] = {
            "target_id": frame.target_id,
            "x": frame.x,
            "y": frame.y,
            "z": frame.z,
            "speed": frame.speed,
            "height": frame.height,
        }

    targets = list(targets_by_id.values())

    presence = (
        any(frame.presence for frame in latest_frames)
        or len(targets) > 0
    )

    return {
        "type": "radar_live",
        "frame_id": latest_frame_id,
        "presence": presence,
        "target_count": len(targets),
        "targets": targets,
    }


async def _flush_loop():
    while True:
        try:
            await aggregator.flush_expired()
        except Exception as exc:
            print(f"[AGGREGATION ERROR] {exc}")

        await asyncio.sleep(0.2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_flush_loop())

    try:
        yield

    finally:
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="CareWave Sensor Ingest API",
    version="1.4.0",
    lifespan=lifespan,
)

app.include_router(control_router)

app.mount(
    "/dashboard-static",
    StaticFiles(
        directory=VISUALIZATION_DIR
    ),
    name="dashboard-static",
)


@app.get(
    "/dashboard",
    include_in_schema=False,
)
def dashboard():
    return FileResponse(
        VISUALIZATION_DIR
        / "index.html"
    )


@app.websocket(
    "/ws/sensor/{sensor_id}"
)
async def sensor_websocket(
    websocket: WebSocket,
    sensor_id: str,
):
    await live_manager.connect(
        sensor_id,
        websocket,
    )

    try:
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        live_manager.disconnect(
            sensor_id,
            websocket,
        )

    except Exception:
        live_manager.disconnect(
            sensor_id,
            websocket,
        )


@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

    return {
        "status": "ok",
        "database": "connected",
    }


@app.post("/api/sensor/frame")
async def receive_sensor_frame(
    frame: RadarFrameIn,
):
    payload = frame.model_dump()

    if payload.get("timestamp") is None:
        payload["timestamp"] = (
            datetime
            .now(KST)
            .replace(tzinfo=None)
        )

    await aggregator.add_frame(payload)

    live_payload = _build_live_payload(
        [frame]
    )

    if live_payload is not None:
        await live_manager.broadcast(
            str(frame.sensor_id),
            live_payload,
        )

    return {
        "status": "accepted",
        "sensor_id": frame.sensor_id,
        "subject_id": frame.subject_id,
        "frame_id": frame.frame_id,
    }


@app.post("/api/sensor/batch")
async def receive_sensor_batch(
    batch: RadarFrameBatchIn,
):
    received_at = (
        datetime
        .now(KST)
        .replace(tzinfo=None)
    )

    payloads = []

    for frame in batch.frames:
        payload = frame.model_dump()

        if payload.get("timestamp") is None:
            payload["timestamp"] = received_at

        payloads.append(payload)

    result = await aggregator.add_batch(
        payloads,
        received_at=received_at,
    )

    first = batch.frames[0]

    live_payload = _build_live_payload(
        batch.frames
    )

    if live_payload is not None:
        await live_manager.broadcast(
            str(first.sensor_id),
            live_payload,
        )

    return {
        "status": "accepted",
        "observation_count": len(batch.frames),
        "frame_count": result["sample_count"],
        "sensor_id": first.sensor_id,
        "subject_id": first.subject_id,
        "first_frame_id": result["first_frame_id"],
        "last_frame_id": result["last_frame_id"],
        "window_start": result["window_start"],
        "window_end": result["window_end"],
    }
