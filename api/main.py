import asyncio
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from sqlalchemy import text

from aggregation.sensor_aggregator import aggregator
from api.schemas import RadarFrameBatchIn, RadarFrameIn
from database.connection import engine


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
    version="1.1.1",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}


@app.post("/api/sensor/frame")
async def receive_sensor_frame(frame: RadarFrameIn):
    await aggregator.add_frame(frame.model_dump())
    return {
        "status": "accepted",
        "sensor_id": frame.sensor_id,
        "subject_id": frame.subject_id,
        "frame_id": frame.frame_id,
    }


@app.post("/api/sensor/batch")
async def receive_sensor_batch(batch: RadarFrameBatchIn):
    # Give every frame in one ESP32 batch the exact same server receive time.
    # This guarantees a 1-second batch is not split across two DB windows
    # just because request processing crosses a second boundary.
    received_at = datetime.now()

    for frame in batch.frames:
        payload = frame.model_dump()
        if payload.get("timestamp") is None:
            payload["timestamp"] = received_at
        await aggregator.add_frame(payload)

    first = batch.frames[0]
    last = batch.frames[-1]

    return {
        "status": "accepted",
        "count": len(batch.frames),
        "sensor_id": first.sensor_id,
        "subject_id": first.subject_id,
        "first_frame_id": first.frame_id,
        "last_frame_id": last.frame_id,
    }
