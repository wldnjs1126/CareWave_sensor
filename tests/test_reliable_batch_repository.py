"""SQLite-only tests. Never touch the NCP database."""
import os
import unittest
from datetime import datetime, timedelta

# The production engine is configured at import; these dummy env vars ensure
# module import succeeds without trying to contact a real database.
for key, value in {
    "DB_HOST": "127.0.0.1", "DB_USER": "unused",
    "DB_PASSWORD": "unused", "DB_NAME": "unused",
}.items():
    os.environ.setdefault(key, value)

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from database.reliable_batch_repository import (
    find_receipt, save_batch_once,
)


class BatchIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        # SQLite-compatible equivalents of the required two InnoDB tables.
        with self.engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE sensor_batch_receipt (
                    batch_id VARCHAR(96) PRIMARY KEY,
                    payload_sha256 CHAR(64) NOT NULL,
                    sensor_id VARCHAR(64) NOT NULL,
                    subject_id VARCHAR(64),
                    first_frame_id BIGINT,
                    last_frame_id BIGINT,
                    window_start DATETIME NOT NULL,
                    window_end DATETIME NOT NULL,
                    sample_count INT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("""
                CREATE TABLE sensor_raw (
                    raw_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sensor_id VARCHAR(64), subject_id VARCHAR(64),
                    window_start DATETIME, window_end DATETIME,
                    sample_count INT, presence INT,
                    avg_x FLOAT, avg_y FLOAT, avg_z FLOAT, min_z FLOAT,
                    avg_velocity_x FLOAT, avg_velocity_y FLOAT,
                    avg_velocity_z FLOAT, min_velocity_z FLOAT,
                    avg_speed FLOAT, max_speed FLOAT,
                    avg_acceleration_z FLOAT, min_acceleration_z FLOAT,
                    avg_height FLOAT, min_height FLOAT,
                    avg_movement_level FLOAT, zone VARCHAR(64),
                    created_at DATETIME
                )
            """))

    @staticmethod
    def sample():
        start = datetime(2026, 10, 20, 18)
        return {
            "sensor_id": 1, "subject_id": 1,
            "window_start": start,
            "window_end": start + timedelta(seconds=1),
            "sample_count": 18, "presence": 1,
            "avg_x": 1.0, "avg_y": 2.0, "avg_z": 0.9,
            "min_z": 0.8, "avg_velocity_x": 0.0,
            "avg_velocity_y": 0.0, "avg_velocity_z": 0.0,
            "min_velocity_z": 0.0, "avg_speed": 0.0, "max_speed": 0.0,
            "avg_acceleration_z": 0.0, "min_acceleration_z": 0.0,
            "avg_height": 1.0, "min_height": 1.0,
            "avg_movement_level": 0.0, "zone": "ROOM",
            "created_at": start + timedelta(seconds=2),
        }

    def test_repeated_same_id_creates_only_one_sensor_raw(self):
        row = self.sample()
        kwargs = dict(
            batch_id="boot_nonce_000001",
            payload_sha256="a" * 64,
            first_frame_id=100, last_frame_id=117,
        )
        first, receipt1 = save_batch_once(self.engine, row, **kwargs)
        second, receipt2 = save_batch_once(self.engine, row, **kwargs)
        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(receipt1["window_start"], receipt2["window_start"])
        self.assertIsNotNone(find_receipt(self.engine, kwargs["batch_id"]))
        with self.engine.connect() as conn:
            n = conn.execute(text("SELECT COUNT(*) FROM sensor_raw")).scalar_one()
        self.assertEqual(n, 1)

    def test_conflicting_id_different_payload_rejected(self):
        row = self.sample()
        save_batch_once(
            self.engine, row, batch_id="boot_nonce_000001",
            payload_sha256="a" * 64, first_frame_id=1, last_frame_id=18,
        )
        with self.assertRaises(ValueError):
            save_batch_once(
                self.engine, row, batch_id="boot_nonce_000001",
                payload_sha256="b" * 64, first_frame_id=1, last_frame_id=18,
            )
        with self.engine.connect() as conn:
            self.assertEqual(
                conn.execute(text("SELECT COUNT(*) FROM sensor_raw")).scalar_one(),
                1,
            )

    def test_failure_rolls_back_receipt_and_sensor_row(self):
        row = self.sample()
        # Make sensor_raw INSERT fail with a real constraint instead.
        with self.engine.begin() as conn:
            conn.execute(text(
                "CREATE TRIGGER stop_sensor_raw BEFORE INSERT ON sensor_raw "
                "BEGIN SELECT RAISE(ABORT, 'write failed'); END"
            ))
        with self.assertRaises(Exception):
            save_batch_once(
                self.engine, row, batch_id="boot_nonce_000002",
                payload_sha256="b" * 64, first_frame_id=19, last_frame_id=36,
            )
        self.assertIsNone(find_receipt(self.engine, "boot_nonce_000002"))
        with self.engine.connect() as conn:
            self.assertEqual(
                conn.execute(text("SELECT COUNT(*) FROM sensor_raw")).scalar_one(),
                0,
            )
        # An orphaned receipt would prevent an authentic retry; confirm
        # that a fixed DB can accept this *same* batch_id after rollback.
        with self.engine.begin() as conn:
            conn.execute(text("DROP TRIGGER stop_sensor_raw"))
        inserted, _ = save_batch_once(
            self.engine, row, batch_id="boot_nonce_000002",
            payload_sha256="b" * 64, first_frame_id=19, last_frame_id=36,
        )
        self.assertTrue(inserted)
        with self.engine.connect() as conn:
            self.assertEqual(
                conn.execute(text("SELECT COUNT(*) FROM sensor_raw")).scalar_one(),
                1,
            )

if __name__ == "__main__":
    unittest.main()
