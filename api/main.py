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

from aggregation.occupancy_state import occupancy_manager
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


def _latest_valid_target(
    frames: list[RadarFrameIn],
) -> dict | None:
    valid = [
        frame
        for frame in frames
        if (
            bool(frame.presence)
            and frame.target_id is not None
            and frame.x is not None
            and frame.y is not None
        )
    ]

    if not valid:
        return None

    frame_ids = [
        frame.frame_id
        for frame in valid
        if frame.frame_id is not None
    ]

    if frame_ids:
        latest_frame_id = max(frame_ids)

        latest = [
            frame
            for frame in valid
            if frame.frame_id == latest_frame_id
        ]
    else:
        latest = valid

    # Current CareWave deployment is a single-person room.
    frame = latest[0]

    return {
        "frame_id": frame.frame_id,
        "target_id": frame.target_id,
        "x": frame.x,
        "y": frame.y,
        "z": frame.z,
        "speed": frame.speed,
        "height": frame.height,
    }


def _update_occupancy(
    *,
    sensor_id,
    subject_id,
    frames: list[RadarFrameIn],
    now: datetime,
) -> dict:
    target = _latest_valid_target(frames)

    detected = target is not None

    return occupancy_manager.update(
        sensor_id=sensor_id,
        subject_id=subject_id,
        detected=detected,
        now=now,
        target_id=(
            target["target_id"]
            if target is not None
            else None
        ),
        x=(
            target["x"]
            if target is not None
            else None
        ),
        y=(
            target["y"]
            if target is not None
            else None
        ),
        z=(
            target["z"]
            if target is not None
            else None
        ),
        speed=(
            target["speed"]
            if target is not None
            else None
        ),
    )


def _build_live_payload(
    frames: list[RadarFrameIn],
    occupancy: dict,
) -> dict | None:
    frame_ids = [
        frame.frame_id
        for frame in frames
        if frame.frame_id is not None
    ]

    if not frame_ids:
        return None

    latest_frame_id = max(frame_ids)

    # Show current target(s) only when they are actually available.
    detected_frames = [
        frame
        for frame in frames
        if (
            bool(frame.presence)
            and frame.target_id is not None
            and frame.x is not None
            and frame.y is not None
        )
    ]

    targets = []

    if detected_frames:
        detected_ids = [
            frame.frame_id
            for frame in detected_frames
            if frame.frame_id is not None
        ]

        if detected_ids:
            latest_detected_id = max(detected_ids)

            latest_detected_frames = [
                frame
                for frame in detected_frames
                if frame.frame_id == latest_detected_id
            ]
        else:
            latest_detected_frames = detected_frames

        targets_by_id: dict[int, dict] = {}

        for frame in latest_detected_frames:
            targets_by_id[frame.target_id] = {
                "target_id": frame.target_id,
                "x": frame.x,
                "y": frame.y,
                "z": frame.z,
                "speed": frame.speed,
                "height": frame.height,
            }

        targets = list(
            targets_by_id.values()
        )

    return {
        "type": "radar_live",
        "frame_id": latest_frame_id,

        # Instant radar target detection:
        "detected": len(targets) > 0,

        # Stateful room occupancy:
        "presence": bool(
            occupancy["present"]
        ),
        "presence_inferred": bool(
            occupancy["inferred"]
        ),
        "occupancy_state": occupancy["mode"],
        "zone": occupancy["zone"],
        "seconds_since_detection": (
            occupancy[
                "seconds_since_detection"
            ]
        ),
        "last_known_position": (
            occupancy[
                "last_known_position"
            ]
        ),

        "target_count": len(targets),
        "targets": targets,
    }


async def _flush_loop():
    while True:
        try:
            await aggregator.flush_expired()
        except Exception as exc:
            print(
                f"[AGGREGATION ERROR] {exc}"
            )

        await asyncio.sleep(0.2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(
        _flush_loop()
    )

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
    version="1.5.0",
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
    received_at = (
        datetime
        .now(KST)
        .replace(tzinfo=None)
    )

    occupancy = _update_occupancy(
        sensor_id=frame.sensor_id,
        subject_id=frame.subject_id,
        frames=[frame],
        now=received_at,
    )

    payload = frame.model_dump()

    if payload.get("timestamp") is None:
        payload["timestamp"] = received_at

    # IMPORTANT:
    # sensor_raw.presence is now ROOM OCCUPANCY,
    # not simply "a target exists in this exact frame".
    payload["presence"] = bool(
        occupancy["present"]
    )

    if occupancy["zone"] is not None:
        payload["zone"] = occupancy["zone"]

    await aggregator.add_frame(payload)

    live_payload = _build_live_payload(
        [frame],
        occupancy,
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
        "occupancy": occupancy["mode"],
        "presence": occupancy["present"],
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

    first = batch.frames[0]

    occupancy = _update_occupancy(
        sensor_id=first.sensor_id,
        subject_id=first.subject_id,
        frames=batch.frames,
        now=received_at,
    )

    payloads = []

    for frame in batch.frames:
        payload = frame.model_dump()

        if payload.get("timestamp") is None:
            payload["timestamp"] = (
                received_at
            )

        # Store inferred occupancy in sensor_raw.
        # X/Y/Z remain measured values only; they are NOT fabricated.
        payload["presence"] = bool(
            occupancy["present"]
        )

        if occupancy["zone"] is not None:
            payload["zone"] = (
                occupancy["zone"]
            )

        payloads.append(payload)

    result = await aggregator.add_batch(
        payloads,
        received_at=received_at,
    )

    live_payload = _build_live_payload(
        batch.frames,
        occupancy,
    )

    if live_payload is not None:
        await live_manager.broadcast(
            str(first.sensor_id),
            live_payload,
        )

    return {
        "status": "accepted",
        "observation_count": len(
            batch.frames
        ),
        "frame_count": result[
            "sample_count"
        ],
        "sensor_id": first.sensor_id,
        "subject_id": first.subject_id,
        "first_frame_id": result[
            "first_frame_id"
        ],
        "last_frame_id": result[
            "last_frame_id"
        ],
        "window_start": result[
            "window_start"
        ],
        "window_end": result[
            "window_end"
        ],
        "occupancy": occupancy["mode"],
        "presence": occupancy["present"],
        "presence_inferred": occupancy[
            "inferred"
        ],
        "zone": occupancy["zone"],
    }
