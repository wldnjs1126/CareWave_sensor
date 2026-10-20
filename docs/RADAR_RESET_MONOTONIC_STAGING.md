# Radar frame reset: monotonic DB window staging test

Scope: **diagnostic branch only**. Do not deploy to operating NCP FastAPI or flash an experimental radar until tests succeed.

## Problem observed

STOP/START reset TI frame counter from 5882 to 1. A previous UART backlog can make the DB last stored window later than the next receive-time candidate; existing DB rebase logic sometimes moved sensor_raw.window_start backwards.

## Diagnostic backend patch

`aggregation/sensor_aggregator.py` now uses the latest **committed** DB end as a monotonic floor when a batch's frame IDs are discontinuous:
- candidate is earlier than latest committed end: `start = latest_end`
- candidate is 0–3 seconds after latest end: maintain continuity
- candidate is more than 3 seconds later: start at receive-time candidate; do not fabricate missing windows.

The patch avoids backward timestamps, but if old rows already extend into the future because of a UART backlog, it may allocate a future window too. This **does not reconstruct true capture time**. The final design needs sensor-generated acquisition timestamps and session IDs, with out-of-order handling. Do not use these temporary rows for AI event scoring.

## Local regression tests without NCP access

From the separate diagnostic clone:

```cmd
cd C:\CareWave_sensor_reliable_test
git pull --ff-only
python -m unittest discover -s tests -v
```

Expected: 5 passing tests. The new `test_frame_counter_reset_does_not_move_db_window_backward` uses the actual FastAPI HTTP handler and in-memory SQLite with a simulated DB window later than incoming receive time.

No `.env` changes, DB writes, migrations, or running-server restarts are necessary.

## Firmware experiment

`CareWave_v5_0_10_clean_session_stage1_TEST.zip` is distributed separately as a bench-only Arduino sketch. It discards UART data collected during blocking CLI configuration and after STOP/START to prevent stale data from flooding normal parsing. This is not a fix for synchronous HTTP UART contention and it deliberately loses some startup data.

Never enable stage 2 / 3D until the batch and timeline tests are stable.
