"""Atomic idempotency receipts for optional client_batch_id payloads.

Both tables MUST be InnoDB. No automatic DDL runs in the API.
Requires manual execution of migrations/20261020_sensor_batch_receipt.sql.
Existing pre-batch_id clients keep using the legacy path unchanged.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from database.sensor_raw_repository import INSERT_SENSOR_RAW


FIND_RECEIPT = text("""
SELECT batch_id, payload_sha256, sensor_id, subject_id,
       first_frame_id, last_frame_id, window_start, window_end, sample_count
FROM sensor_batch_receipt WHERE batch_id=:batch_id
""")

INSERT_RECEIPT = text("""
INSERT INTO sensor_batch_receipt (
    batch_id, payload_sha256, sensor_id, subject_id, first_frame_id,
    last_frame_id, window_start, window_end, sample_count
) VALUES (
    :batch_id, :payload_sha256, :sensor_id, :subject_id, :first_frame_id,
    :last_frame_id, :window_start, :window_end, :sample_count
)
""")


def find_receipt(db_engine, batch_id: str):
    with db_engine.connect() as conn:
        row = conn.execute(FIND_RECEIPT, {"batch_id": batch_id}).mappings().first()
        return dict(row) if row else None


def _assert_same(receipt: dict, expected_digest: str, sensor_id, subject_id):
    if (receipt["payload_sha256"] != expected_digest or
        str(receipt["sensor_id"]) != str(sensor_id) or
        (str(receipt["subject_id"]) if receipt["subject_id"] is not None else None)
            != (str(subject_id) if subject_id is not None else None)):
        raise ValueError("batch_id already belongs to different data")


def save_batch_once(
    db_engine, row: dict, *, batch_id: str, payload_sha256: str,
    first_frame_id, last_frame_id,
) -> tuple[bool, dict]:
    """Save receipt and sensor_raw in the SAME transaction, exactly once.

    Concurrent duplicate requests serialize on the batch_id unique key.
    The savepoint handles a duplicate key without aborting the outer
    transaction. Return (inserted, saved_receipt).
    """
    identity = {
        "batch_id": batch_id,
        "payload_sha256": payload_sha256,
        "sensor_id": str(row["sensor_id"]),
        "subject_id": (str(row["subject_id"])
                       if row["subject_id"] is not None else None),
        "first_frame_id": first_frame_id,
        "last_frame_id": last_frame_id,
        "window_start": row["window_start"],
        "window_end": row["window_end"],
        "sample_count": row["sample_count"],
    }
    with db_engine.begin() as conn:
        try:
            with conn.begin_nested():  # SAVEPOINT: isolated uniqueness conflict
                conn.execute(INSERT_RECEIPT, identity)
        except IntegrityError:
            stored_row = conn.execute(
                FIND_RECEIPT, {"batch_id": batch_id}
            ).mappings().first()
            if stored_row is None:
                raise  # not our batch_id conflict
            stored = dict(stored_row)
            _assert_same(stored, payload_sha256, row["sensor_id"], row["subject_id"])
            return False, stored
        conn.execute(INSERT_SENSOR_RAW, row)
        return True, identity
