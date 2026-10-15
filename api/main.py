import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from sqlalchemy import text

from aggregation.sensor_aggregator import aggregator
from api.schemas import RadarFrameBatchIn, RadarFrameIn
from database.connection import engine


KST = ZoneInfo("Asia/Seoul")


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
    version="1.2.1",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}


@app.post("/api/sensor/frame")
async def receive_sensor_frame(frame: RadarFrameIn):
    payload = frame.model_dump()
    if payload.get("timestamp") is None:
        payload["timestamp"] = datetime.now(KST).replace(tzinfo=None)

    await aggregator.add_frame(payload)

    return {
        "status": "accepted",
        "sensor_id": frame.sensor_id,
        "subject_id": frame.subject_id,
        "frame_id": frame.frame_id,
    }


@app.post("/api/sensor/batch")
async def receive_sensor_batch(batch: RadarFrameBatchIn):
    received_at = datetime.now(KST).replace(tzinfo=None)

    for frame in batch.frames:
        payload = frame.model_dump()
        if payload.get("timestamp") is None:
            payload["timestamp"] = received_at
        await aggregator.add_frame(payload)

    first = batch.frames[0]
    last = batch.frames[-1]

    frame_ids = [frame.frame_id for frame in batch.frames]
    non_null_frame_ids = {frame_id for frame_id in frame_ids if frame_id is not None}
    frame_count = len(non_null_frame_ids) if non_null_frame_ids else len(batch.frames)

    return {
        "status": "accepted",
        "observation_count": len(batch.frames),
        "frame_count": frame_count,
        "sensor_id": first.sensor_id,
        "subject_id": first.subject_id,
        "first_frame_id": first.frame_id,
        "last_frame_id": last.frame_id,
    }
