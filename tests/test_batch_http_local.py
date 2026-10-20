"""Local in-memory ASGI /api/sensor/batch retry test.

No NCP connection, no file-based database, no external HTTP requests.
Run from repository root:
    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

# Override even pre-existing .env values for THIS TEST PROCESS to ensure the
# connection module never even constructs an NCP database URL.
os.environ.update({
    "DB_HOST": "127.0.0.1",
    "DB_PORT": "3306",
    "DB_USER": "no_remote_db",
    "DB_PASSWORD": "no_remote_db",
    "DB_NAME": "no_remote_db",
})

try:
    import httpx
except ImportError:
    httpx = None

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from aggregation.sensor_aggregator import SensorAggregator
from api import main as main_module
from database import sensor_raw_repository as raw_repo
from aggregation import sensor_aggregator as agg_module


@unittest.skipUnless(httpx is not None, "pip install httpx to run ASGI tests")
class LocalBatchHTTPTests(unittest.TestCase):
    def setUp(self):
        self.sqlite_engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        with self.sqlite_engine.begin() as conn:
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
                    sample_count INTEGER NOT NULL,
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

        self.agg = SensorAggregator()
        self.occupancy_result = {
            "mode": "ABSENT", "present": False, "inferred": False,
            "zone": "ROOM", "seconds_since_detection": None,
            "last_known_position": None,
        }
        self.patches = [
            patch.object(main_module, "engine", self.sqlite_engine),
            patch.object(agg_module, "engine", self.sqlite_engine),
            patch.object(raw_repo, "engine", self.sqlite_engine),
            patch.object(main_module, "aggregator", self.agg),
            patch.object(
                main_module, "_update_occupancy",
                return_value=self.occupancy_result,
            ),
            patch.object(main_module.live_manager, "broadcast",
                         new_callable=AsyncMock),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.sqlite_engine.dispose()

    @staticmethod
    def payload():
        return {
            "batch_id": "local_http_test_boot0001_batch0001",
            "frames": [
                {
                    "sensor_id": 1,
                    "subject_id": 1,
                    "frame_id": n,
                    "presence": False,
                    "zone": "ROOM",
                }
                for n in range(1, 19)
            ],
        }

    def counts(self):
        with self.sqlite_engine.connect() as conn:
            rows = conn.execute(
                text("SELECT COUNT(*) FROM sensor_raw")
            ).scalar_one()
            receipts = conn.execute(
                text("SELECT COUNT(*) FROM sensor_batch_receipt")
            ).scalar_one()
            return rows, receipts

    def test_post_retry_is_idempotent_and_conflict_is_409(self):
        async def do_requests():
            transport = httpx.ASGITransport(app=main_module.app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://local-test",
            ) as client:
                payload = self.payload()
                first = await client.post("/api/sensor/batch", json=payload)
                second = await client.post("/api/sensor/batch", json=payload)
                modified = self.payload()
                modified["frames"][0]["x"] = 2.5
                conflicting = await client.post(
                    "/api/sensor/batch", json=modified
                )
                return first, second, conflicting

        first, second, conflicting = asyncio.run(do_requests())
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(conflicting.status_code, 409, conflicting.text)
        self.assertIs(first.json()["duplicate"], False)
        self.assertIs(second.json()["duplicate"], True)
        self.assertEqual(first.json()["window_start"],
                         second.json()["window_start"])
        self.assertEqual(first.json()["window_end"],
                         second.json()["window_end"])
        self.assertEqual(self.counts(), (1, 1))
        self.assertEqual(len(self.agg._batch_state), 1)
        self.assertEqual(
            main_module._update_occupancy.call_count, 1,
            "a duplicate must not update occupancy again",
        )
        self.assertEqual(
            main_module.live_manager.broadcast.await_count, 1,
            "a duplicate must not broadcast a fresh live radar update",
        )


if __name__ == "__main__":
    unittest.main()
