from __future__ import annotations

import asyncio
import math
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from database.sensor_raw_repository import save_sensor_raw


KST = ZoneInfo("Asia/Seoul")
WINDOW_SECONDS = 1


def _now_kst_naive() -> datetime:
    """Return current Korea time as a naive datetime for MySQL DATETIME."""
    return datetime.now(KST).replace(tzinfo=None)


def _normalize_timestamp(value: datetime | None) -> datetime:
    """Normalize an incoming timestamp to Korea time without tzinfo."""
    if value is None:
        return _now_kst_naive()

    if value.tzinfo is not None:
        return value.astimezone(KST).replace(tzinfo=None)

    # Naive timestamps are treated as Korea local time.
    return value


def _window_start(timestamp: datetime) -> datetime:
    """Floor a timestamp to an exact whole-second boundary."""
    return timestamp.replace(microsecond=0)


def _avg(values):
    vals = [v for v in values if v is not None]
    return (sum(vals) / len(vals)) if vals else None


def _min(values):
    vals = [v for v in values if v is not None]
    return min(vals) if vals else None


def _max(values):
    vals = [v for v in values if v is not None]
    return max(vals) if vals else None


def _mode(values):
    vals = [v for v in values if v not in (None, "")]
    if not vals:
        return None
    return Counter(vals).most_common(1)[0][0]


class SensorAggregator:
    def __init__(self):
        # key = (sensor_id, subject_id, exact_window_start)
        self._buffers: dict[
            tuple[int, int | None, datetime],
            list[dict],
        ] = {}
        self._lock = asyncio.Lock()

    async def add_frame(self, frame: dict) -> None:
        timestamp = _normalize_timestamp(frame.get("timestamp"))
        start = _window_start(timestamp)

        sensor_id = frame["sensor_id"]
        subject_id = frame.get("subject_id")
        key = (sensor_id, subject_id, start)

        vx = frame.get("velocity_x")
        vy = frame.get("velocity_y")
        vz = frame.get("velocity_z")

        speed = frame.get("speed")
        if speed is None and None not in (vx, vy, vz):
            speed = math.sqrt(vx * vx + vy * vy + vz * vz)

        movement_level = frame.get("movement_level")
        if movement_level is None:
            movement_level = speed

        sample = dict(frame)
        sample["timestamp"] = timestamp
        sample["speed"] = speed
        sample["movement_level"] = movement_level

        async with self._lock:
            self._buffers.setdefault(key, []).append(sample)

    async def flush_expired(self) -> int:
        now = _now_kst_naive()
        ready: list[
            tuple[
                tuple[int, int | None],
                list[dict],
                datetime,
                datetime,
            ]
        ] = []

        async with self._lock:
            for buffer_key in list(self._buffers.keys()):
                sensor_id, subject_id, start = buffer_key
                end = start + timedelta(seconds=WINDOW_SECONDS)

                if now >= end:
                    frames = self._buffers.pop(buffer_key, [])
                    if frames:
                        ready.append(
                            (
                                (sensor_id, subject_id),
                                frames,
                                start,
                                end,
                            )
                        )

        for key, frames, start, end in ready:
            row = self._aggregate(key, frames, start, end)
            await asyncio.to_thread(save_sensor_raw, row)

        return len(ready)

    def _aggregate(
        self,
        key: tuple[int, int | None],
        frames: list[dict],
        start: datetime,
        end: datetime,
    ) -> dict:
        sensor_id, subject_id = key

        presence_ratio = (
            sum(1 for f in frames if bool(f.get("presence")))
            / len(frames)
        )

        return {
            "sensor_id": sensor_id,
            "subject_id": subject_id,
            "window_start": start,
            "window_end": end,
            "sample_count": len(frames),
            "presence": 1 if presence_ratio >= 0.5 else 0,
            "avg_x": _avg([f.get("x") for f in frames]),
            "avg_y": _avg([f.get("y") for f in frames]),
            "avg_z": _avg([f.get("z") for f in frames]),
            "min_z": _min([f.get("z") for f in frames]),
            "avg_velocity_x": _avg([f.get("velocity_x") for f in frames]),
            "avg_velocity_y": _avg([f.get("velocity_y") for f in frames]),
            "avg_velocity_z": _avg([f.get("velocity_z") for f in frames]),
            "min_velocity_z": _min([f.get("velocity_z") for f in frames]),
            "avg_speed": _avg([f.get("speed") for f in frames]),
            "max_speed": _max([f.get("speed") for f in frames]),
            "avg_acceleration_z": _avg([f.get("acceleration_z") for f in frames]),
            "min_acceleration_z": _min([f.get("acceleration_z") for f in frames]),
            "avg_height": _avg([f.get("height") for f in frames]),
            "min_height": _min([f.get("height") for f in frames]),
            "avg_movement_level": _avg([f.get("movement_level") for f in frames]),
            "zone": _mode([f.get("zone") for f in frames]),
            "created_at": _now_kst_naive(),
        }


aggregator = SensorAggregator()
