from __future__ import annotations

import asyncio
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from database.sensor_raw_repository import save_sensor_raw


KST = ZoneInfo("Asia/Seoul")
WINDOW_SECONDS = 1


def _now_kst_naive() -> datetime:
    return datetime.now(KST).replace(tzinfo=None)


def _normalize_timestamp(value: datetime | None) -> datetime:
    if value is None:
        return _now_kst_naive()

    if value.tzinfo is not None:
        return value.astimezone(KST).replace(tzinfo=None)

    return value


def _window_start(timestamp: datetime) -> datetime:
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
            tuple[object, object | None, datetime],
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
        ready = []

        async with self._lock:
            for buffer_key in list(self._buffers.keys()):
                sensor_id, subject_id, start = buffer_key
                end = start + timedelta(seconds=WINDOW_SECONDS)

                if now >= end:
                    samples = self._buffers.pop(buffer_key, [])
                    if samples:
                        ready.append(
                            (
                                (sensor_id, subject_id),
                                samples,
                                start,
                                end,
                            )
                        )

        for key, samples, start, end in ready:
            row = self._aggregate(key, samples, start, end)
            await asyncio.to_thread(save_sensor_raw, row)

        return len(ready)

    def _group_by_frame(self, samples: list[dict]) -> list[list[dict]]:
        """
        Multiple TIDs can exist in one radar frame.
        Group target observations that share the same frame_id so sample_count
        remains the number of actual radar frames, not the number of targets.
        """
        grouped: dict[object, list[dict]] = defaultdict(list)

        for index, sample in enumerate(samples):
            frame_id = sample.get("frame_id")
            key = ("frame", frame_id) if frame_id is not None else ("sample", index)
            grouped[key].append(sample)

        return list(grouped.values())

    def _summarize_frame(self, observations: list[dict]) -> dict:
        """Create one summary from every target observation in one radar frame."""
        return {
            "presence": any(bool(o.get("presence")) for o in observations),
            "avg_x": _avg([o.get("x") for o in observations]),
            "avg_y": _avg([o.get("y") for o in observations]),
            "avg_z": _avg([o.get("z") for o in observations]),
            "min_z": _min([o.get("z") for o in observations]),
            "avg_velocity_x": _avg([o.get("velocity_x") for o in observations]),
            "avg_velocity_y": _avg([o.get("velocity_y") for o in observations]),
            "avg_velocity_z": _avg([o.get("velocity_z") for o in observations]),
            "min_velocity_z": _min([o.get("velocity_z") for o in observations]),
            "avg_speed": _avg([o.get("speed") for o in observations]),
            "max_speed": _max([o.get("speed") for o in observations]),
            "avg_acceleration_z": _avg([o.get("acceleration_z") for o in observations]),
            "min_acceleration_z": _min([o.get("acceleration_z") for o in observations]),
            "avg_height": _avg([o.get("height") for o in observations]),
            "min_height": _min([o.get("height") for o in observations]),
            "avg_movement_level": _avg([o.get("movement_level") for o in observations]),
            "zone": _mode([o.get("zone") for o in observations]),
        }

    def _aggregate(
        self,
        key: tuple[object, object | None],
        samples: list[dict],
        start: datetime,
        end: datetime,
    ) -> dict:
        sensor_id, subject_id = key

        frame_groups = self._group_by_frame(samples)
        frame_summaries = [self._summarize_frame(group) for group in frame_groups]

        presence_ratio = (
            sum(1 for frame in frame_summaries if frame["presence"])
            / len(frame_summaries)
        )

        return {
            "sensor_id": sensor_id,
            "subject_id": subject_id,
            "window_start": start,
            "window_end": end,
            "sample_count": len(frame_summaries),
            "presence": 1 if presence_ratio >= 0.5 else 0,
            "avg_x": _avg([f.get("avg_x") for f in frame_summaries]),
            "avg_y": _avg([f.get("avg_y") for f in frame_summaries]),
            "avg_z": _avg([f.get("avg_z") for f in frame_summaries]),
            "min_z": _min([f.get("min_z") for f in frame_summaries]),
            "avg_velocity_x": _avg([f.get("avg_velocity_x") for f in frame_summaries]),
            "avg_velocity_y": _avg([f.get("avg_velocity_y") for f in frame_summaries]),
            "avg_velocity_z": _avg([f.get("avg_velocity_z") for f in frame_summaries]),
            "min_velocity_z": _min([f.get("min_velocity_z") for f in frame_summaries]),
            "avg_speed": _avg([f.get("avg_speed") for f in frame_summaries]),
            "max_speed": _max([f.get("max_speed") for f in frame_summaries]),
            "avg_acceleration_z": _avg([f.get("avg_acceleration_z") for f in frame_summaries]),
            "min_acceleration_z": _min([f.get("min_acceleration_z") for f in frame_summaries]),
            "avg_height": _avg([f.get("avg_height") for f in frame_summaries]),
            "min_height": _min([f.get("min_height") for f in frame_summaries]),
            "avg_movement_level": _avg([f.get("avg_movement_level") for f in frame_summaries]),
            "zone": _mode([f.get("zone") for f in frame_summaries]),
            "created_at": _now_kst_naive(),
        }


aggregator = SensorAggregator()
