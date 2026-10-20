"""Idempotent receipt and sensor_raw writes (test branch only).

The receipt and sensor_raw tables must both be InnoDB in production.
No DDL is executed by this module. The migration is manual.
"""
from __future__ import annotations

from datetime import datetime

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


def _normalize_receipt(receipt: dict) -> dict:
    """Keep a consistent datetime result with SQLite and MySQL drivers.

    SQLite's untyped text() query may return timestamp strings; MySQL normally
    returns Python datetime. Normalizing makes retry responses consistent.
    """
    result = dict(receipt)
    for field in ("window_start", "window_end"):
        value = result[field]
        if isinstance(value, str):
            result[field] = datetime.fromisoformat(value)
    return result


def find_receipt(db_engine, batch_id: str):
    with db_engine.connect() as conn:
        row = conn.execute(
            FIND_RECEIPT, {"batch_id": batch_id}
        ).mappings().first()
    return _normalize_receipt(row) if row else None


def _assert_same(receipt: dict, expected_digest: str, sensor_id, subject_id):
    actual_subject = (
        str(receipt["subject_id"]) if receipt["subject_id"] is not None else None
    )
    expected_subject = str(subject_id) if subject_id is not None else None
    if (
        receipt["payload_sha256"] != expected_digest
        or str(receipt["sensor_id"]) != str(sensor_id)
        or actual_subject != expected_subject
    ):
        raise ValueError("batch_id already belongs to different data")


def save_batch_once(
    db_engine, row: dict, *, batch_id: str, payload_sha256: str,
    first_frame_id, last_frame_id,
) -> tuple[bool, dict]:
    """Atomically save one source batch; acknowledge committed duplicates.

    No SAVEPOINT: a SQLite SAVEPOINT can be released before the underlying
    connection starts a real transaction, leaving an orphaned receipt if the
    later sensor_raw insert fails.

    A primary-key conflict triggers rollback of the whole transaction. Only
    then do we query the committed receipt through a new connection.
    InnoDB's unique key serializes concurrent inserts of the same batch_id.
    """
    identity = {
        "batch_id": batch_id,
        "payload_sha256": payload_sha256,
        "sensor_id": str(row["sensor_id"]),
        "subject_id": (
            str(row["subject_id"]) if row["subject_id"] is not None else None
        ),
        "first_frame_id": first_frame_id,
        "last_frame_id": last_frame_id,
        "window_start": row["window_start"],
        "window_end": row["window_end"],
        "sample_count": row["sample_count"],
    }
    try:
        with db_engine.begin() as conn:
            conn.execute(INSERT_RECEIPT, identity)
            conn.execute(INSERT_SENSOR_RAW, row)
    except IntegrityError:
        # The transaction has been rolled back by exiting db_engine.begin().
        # A duplicate key is success only when the committed receipt matches.
        stored = find_receipt(db_engine, batch_id)
        if stored is None:
            raise
        _assert_same(
            stored, payload_sha256, row["sensor_id"], row["subject_id"]
        )
        return False, stored

    return True, identity
