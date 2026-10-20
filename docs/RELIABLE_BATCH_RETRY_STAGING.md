# Reliable batch retry: STAGING ONLY (2026-10-20)

## What is implemented

- Optional `batch_id` on `POST /api/sensor/batch`. The old `frames`-only clients still work exactly as before.
- New migration file: `migrations/20261020_sensor_batch_receipt.sql`.
- Server stores one receipt and its matching `sensor_raw` row **atomically** in an InnoDB transaction.
- A retry with the same ID and same original payload returns `duplicate=true` and the original saved window, with no new `sensor_raw` insert.
- A retry with the same ID but different source frame payload returns HTTP 409.
- SQLite unit tests check duplicate handling, conflicting contents and transaction rollback.
- A separate v5.0.7 firmware TEST ZIP creates boot-nonce-based unique batch IDs and a bounded 8-slot RAM queue. Batch pacing still follows the 55ms radar frame interval.

## Do NOT yet deploy this to the production radar

The server still timestamps new rows largely from SERVER RECEIVE TIME, so batches
replayed following a long Wi-Fi outage may get misleading window_start labels.
An eight-batch queue can overflow, and is lost on ESP32 reboot.
HTTP is still synchronous in the Arduino loop. Therefore this is only a
short-interruption/retry proof-of-concept, not a fully durable medical sensor pipeline.

## Preparation: separate local TEST checkout

```cmd
cd C:\
git clone --branch diagnostic/sensor-batch-timeline-20261020 --single-branch https://github.com/wldnjs1126/CareWave_sensor.git CareWave_sensor_reliable_test
cd C:\CareWave_sensor_reliable_test
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

These tests use in-memory SQLite only and must not write to NCP.
The service connection module may need the existing .env in a controlled
server clone for integration, but DO NOT put credentials into GitHub.

## Controlled server rollout only AFTER unit tests

1. Create a dedicated TEST NCP MySQL database or copy of schema. Do not reuse current production sensor_raw.
2. Verify both sensor_raw and the receipt table use InnoDB. Apply the migration SQL manually in TEST.
3. Deploy the diagnostic branch to a separate test FastAPI server endpoint.
4. Send a small test batch with one unique batch_id; verify success and exactly one sensor_raw+receipt record.
5. Send the exact same JSON again; verify duplicate=true and counts unchanged.
6. Send the same ID with changed sensor data; verify HTTP 409 and counts unchanged.
7. Only then flash v5.0.7 ZIP with TEST API_URL. Its `carewave_secrets.h` contains placeholders; never publish the filled header.
8. During a brief Wi-Fi outage, confirm QUEUE_RETRY and QUEUE_ACK; ensure DB has no duplicates.
9. Also check window_start against received-at wall time before considering any live production deployment.

## Current constraints and future design

- Frame acquisition timestamp per batch must be recorded and validated separately from HTTP received_at for trustworthy store-and-forward.
- Protect true source ordering when retry queue drains after downtime (the server's current drift rebase is unsuitable for long backlog replay).
- Add explicit queue saturation monitoring, restart-safe persistence, and a separate network transmit task.
- Once the capture-time and transport semantics are correct, retest 3D live and remote control together.
- Do NOT invent missing zero-speed windows for inactivity or fall detection.

## SQLite unit-test fix (2026-10-20)

The first local Windows run produced 1 PASS / 2 FAIL. An explicit
SAVEPOINT (begin_nested) let a receipt survive a later sensor_raw insert
failure on SQLite, invalidating rollback tests. This is a real test-safety bug.
The server now uses a single outer db_engine.begin() transaction with no
SAVEPOINT; on IntegrityError the whole transaction is rolled back before a
new lookup of the committed receipt. Driver-dependent receipt datetime values
are also normalized. The rollback test was strengthened to retry the same ID
after repairing the injected failure.

The isolated local simulation of SQLite full transaction, duplicate retry,
rollback, and conflicting payload passed. However the complete three-test
suite still needs to be run by the user on the updated branch; a production
MySQL InnoDB integration test remains pending. **Do not apply this migration
or flash the v5.0.7 firmware to the production sensor until these pass.**
