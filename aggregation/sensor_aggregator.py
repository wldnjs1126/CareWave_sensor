from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from database.sensor_raw_repository import (
    get_latest_window_end,
    save_sensor_raw,
)
from database.connection import engine
from database.reliable_batch_repository import (
    _assert_same, find_receipt, save_batch_once,
)


KST = ZoneInfo("Asia/Seoul")
WINDOW_SECONDS = 1
BATCH_CONTINUITY_TOLERANCE_SECONDS = 3
# Diagnostics only: never changes the aggregation or timestamps.
BATCH_TIMELINE_DEBUG = os.getenv("CAREWAVE_BATCH_TIMELINE_DEBUG", "0") == "1"
logger = logging.getLogger(__name__)


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
        # Legacy single-frame endpoint buffer.
        # key = (sensor_id, subject_id, exact_window_start)
        self._buffers: dict[
            tuple[object, object | None, datetime],
            list[dict],
        ] = {}

        # Batch endpoint continuity state.
        # key = (sensor_id, subject_id)
        # value = {"next_start": datetime, "last_frame_id": int | None}
        self._batch_state: dict[
            tuple[object, object | None],
            dict,
        ] = {}

        self._lock = asyncio.Lock()

    def _prepare_sample(self, frame: dict) -> dict:
        timestamp = _normalize_timestamp(frame.get("timestamp"))

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

        return sample

    async def add_frame(self, frame: dict) -> None:
        sample = self._prepare_sample(frame)

        timestamp = sample["timestamp"]
        start = _window_start(timestamp)

        sensor_id = sample["sensor_id"]
        subject_id = sample.get("subject_id")
        key = (sensor_id, subject_id, start)

        async with self._lock:
            self._buffers.setdefault(key, []).append(sample)

    async def add_batch(
        self,
        frames: list[dict],
        received_at: datetime | None = None,
        *,
        batch_id: str | None = None,
        payload_sha256: str | None = None,
    ) -> dict:
        """
        Treat one ESP32 batch as one physical ~1 second sensor_raw window.

        If radar frame IDs are continuous between batches, the next DB window
        starts exactly where the previous one ended. This removes artificial
        one-second holes caused only by HTTP/server arrival jitter.

        If frame IDs are not continuous, we do NOT fabricate missing data.
        The timeline is realigned to the current receive time, so a genuine
        dropped batch/network outage can still appear as a real gap.
        """
        if not frames:
            raise ValueError("batch must contain at least one frame")

        received_at = _normalize_timestamp(received_at)
        samples = [self._prepare_sample(frame) for frame in frames]

        sensor_id = samples[0]["sensor_id"]
        subject_id = samples[0].get("subject_id")
        key = (sensor_id, subject_id)

        for sample in samples:
            if (
                sample["sensor_id"] != sensor_id
                or sample.get("subject_id") != subject_id
            ):
                raise ValueError(
                    "all observations in one batch must share sensor_id and subject_id"
                )

        frame_ids = [
            sample.get("frame_id")
            for sample in samples
            if sample.get("frame_id") is not None
        ]

        first_frame_id = frame_ids[0] if frame_ids else None
        last_frame_id = frame_ids[-1] if frame_ids else None

        # The batch contains roughly the preceding one second of radar data.
        candidate_start = _window_start(
            received_at - timedelta(seconds=WINDOW_SECONDS)
        )

        if batch_id is not None and not payload_sha256:
            raise ValueError("payload_sha256 required with batch_id")

        precomputed_row = None
        write_elapsed_ms = 0.0
        async with self._lock:
            if batch_id is not None:
                cached = await asyncio.to_thread(find_receipt, engine, batch_id)
                if cached is not None:
                    _assert_same(cached, payload_sha256, sensor_id, subject_id)
                    return {
                        "window_start": cached["window_start"],
                        "window_end": cached["window_end"],
                        "sample_count": cached["sample_count"],
                        "first_frame_id": cached["first_frame_id"],
                        "last_frame_id": cached["last_frame_id"],
                        "duplicate": True,
                    }
            state = self._batch_state.get(key)
            previous_last_frame_id = (
                state.get("last_frame_id") if state is not None else None
            )
            previous_received_at = (
                state.get("last_received_at") if state is not None else None
            )
            previous_next_start = (
                state.get("next_start") if state is not None else None
            )
            drift_seconds = (
                (candidate_start - previous_next_start).total_seconds()
                if previous_next_start is not None else None
            )
            receive_interval_seconds = (
                (received_at - previous_received_at).total_seconds()
                if previous_received_at is not None else None
            )
            allocation_reason = "INITIAL_BATCH"

            frame_sequence_continuous = (
                state is not None
                and state.get("last_frame_id") is not None
                and first_frame_id is not None
                and first_frame_id == state["last_frame_id"] + 1
            )

            if frame_sequence_continuous:
                drift_seconds = (
                    candidate_start - state["next_start"]
            ).total_seconds()

                if drift_seconds > 3:
                    # Existing clock realignment is preserved for diagnosis.
                    allocation_reason = "FRAME_CONTINUOUS_BUT_DRIFT_REBASE"
                    start = candidate_start
                else:
                    allocation_reason = "FRAME_CONTINUOUS"
                    start = state["next_start"]

            else:
                if previous_last_frame_id is None or first_frame_id is None:
                    allocation_reason = "FRAME_SEQUENCE_UNAVAILABLE"
                else:
                    allocation_reason = "FRAME_SEQUENCE_DISCONTINUOUS"
                latest_end = await asyncio.to_thread(
                    get_latest_window_end,
                    sensor_id,
                    subject_id,
                )

                # On a normal service restart, continue from the latest DB row
                # if it is close to the current batch time. On a long outage,
                # realign to current time instead of inventing many seconds.
                if latest_end is not None:
                    time_difference = abs(
                        (candidate_start - latest_end).total_seconds()
                    )

                    if time_difference <= BATCH_CONTINUITY_TOLERANCE_SECONDS:
                        start = latest_end
                        allocation_reason += "_DB_WINDOW_CONTINUITY"
                    else:
                        start = candidate_start
                        allocation_reason += "_DB_TIME_REBASE"
                else:
                    start = candidate_start
                    allocation_reason += "_NO_DB_PREVIOUS"

            end = start + timedelta(seconds=WINDOW_SECONDS)

            if batch_id is not None:
                # Persist the receipt and sensor_raw atomically before advancing
                # the in-memory cursor. Unique batch_id prevents duplicate rows
                # after an HTTP response is lost and the client retries.
                precomputed_row = self._aggregate(key, samples, start, end)
                db_write_start = time.perf_counter()
                inserted, stored = await asyncio.to_thread(
                    save_batch_once, engine, precomputed_row,
                    batch_id=batch_id,
                    payload_sha256=payload_sha256,
                    first_frame_id=first_frame_id,
                    last_frame_id=last_frame_id,
                )
                write_elapsed_ms = (
                    time.perf_counter() - db_write_start
                ) * 1000.0
                if not inserted:
                    return {
                        "window_start": stored["window_start"],
                        "window_end": stored["window_end"],
                        "sample_count": stored["sample_count"],
                        "first_frame_id": stored["first_frame_id"],
                        "last_frame_id": stored["last_frame_id"],
                        "duplicate": True,
                    }

            self._batch_state[key] = {
                "next_start": end,
                "last_frame_id": last_frame_id,
                # Only used for diagnostics; not aggregation decisions.
                "last_received_at": received_at,
            }

        row = precomputed_row or self._aggregate(
            key, samples, start, end,
        )

        if batch_id is None:
            db_write_start = time.perf_counter()
            await asyncio.to_thread(save_sensor_raw, row)
            write_elapsed_ms = (
                time.perf_counter() - db_write_start
            ) * 1000.0
        db_write_ms = round(write_elapsed_ms, 1)

        if BATCH_TIMELINE_DEBUG:
            # Read these alongside ESP32 HTTP response/frame counters.
            # No raw position or personal movement coordinates are logged.
            diagnostic = {
                "sensor_id": sensor_id,
                "subject_id": subject_id,
                "reason": allocation_reason,
                "received_at": received_at.isoformat(sep=" "),
                "receive_interval_seconds": receive_interval_seconds,
                "first_frame_id": first_frame_id,
                "last_frame_id": last_frame_id,
                "previous_last_frame_id": previous_last_frame_id,
                "frame_gap_count": (
                    max(0, first_frame_id - previous_last_frame_id - 1)
                    if first_frame_id is not None
                    and previous_last_frame_id is not None else None
                ),
                "observation_count": len(samples),
                "sample_count": row["sample_count"],
                "candidate_start": candidate_start.isoformat(sep=" "),
                "previous_next_start": (
                    previous_next_start.isoformat(sep=" ")
                    if previous_next_start is not None else None
                ),
                "drift_seconds": drift_seconds,
                "assigned_start": start.isoformat(sep=" "),
                "assigned_end": end.isoformat(sep=" "),
                "db_write_ms": db_write_ms,
            }
            logger.warning(
                "CAREWAVE_BATCH_TIMELINE %s",
                json.dumps(diagnostic, ensure_ascii=False),
            )

        return {
            "window_start": start,
            "window_end": end,
            "sample_count": row["sample_count"],
            "first_frame_id": first_frame_id,
            "last_frame_id": last_frame_id,
            "duplicate": False,
        }

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
            group_key = (
                ("frame", frame_id)
                if frame_id is not None
                else ("sample", index)
            )
            grouped[group_key].append(sample)

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
        frame_summaries = [
            self._summarize_frame(group)
            for group in frame_groups
        ]

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
