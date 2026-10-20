# Local API idempotency test without NCP privileges

Why: NCP MySQL account cannot CREATE TABLE in the new test DB; do not change the user's existing production `sensor_raw`, NCP users, DB account permissions, or the operating ESP32 while verifying the retry code.

Run only from the separate local `C:\CareWave_sensor_reliable_test` clone:

```cmd
cd C:\CareWave_sensor_reliable_test
git pull --ff-only
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -v
```

The new `tests/test_batch_http_local.py` actually calls FastAPI's `POST /api/sensor/batch` handler using `httpx.ASGITransport` (no listening socket, no external HTTP). It replaces the API and aggregator's DB engines with **in-memory SQLite**, overrides the DB variables for this test process with dummy localhost values, and patches occupancy broadcasting to avoid side effects.

Expected additional test: `test_post_retry_is_idempotent_and_conflict_is_409`.

The HTTP test verifies HTTP 200 on first batch, HTTP 200 and `duplicate=true` on identical retry, HTTP 409 on reused ID with modified payload; ensures there is exactly one `sensor_raw` and one receipt, and occupancy updates and live broadcasts only once.

If any test fails, STOP: do not flash v5.0.7 or deploy the branch. Share the entire traceback. SQLite ASGI success is not MySQL InnoDB integration proof.

Reminder: v5.0.6 remains the running diagnostic firmware; no real-life monitoring validation, persistence on ESP reboot, or original capture-time replay has been proven. HTTP retry must be tested on a truly isolated MySQL environment before production.
