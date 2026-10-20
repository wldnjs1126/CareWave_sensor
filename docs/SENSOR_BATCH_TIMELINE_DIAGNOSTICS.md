# CareWave 4-second sensor_raw gaps: server-side diagnosis

## Evidence from October 20, 2026
- CSV 1 has 322 sensor_raw rows and 14 gaps, each with four seconds of absent window labels.
- raw_id increments by one across each gap; created_at advances approximately two seconds while window_start advances five seconds.
- Mean database insertion interval is about 1.174 seconds. The existing aggregator labels one HTTP batch as exactly one second.
- On continuous radar frame IDs, the server explicitly REBASES a window to receive time when clock drift exceeds three seconds.
- This is consistent with a **timestamp-label jump**, not proof of an ESP32 receive failure or proof that all radar frames arrived.

## Opt-in diagnostic branch
diagnostic/sensor-batch-timeline-20261020

Only logs are added; existing sensor_raw writes/timestamps remain unchanged.
Run backend on a controlled Linux test deployment with environment setting:

CAREWAVE_BATCH_TIMELINE_DEBUG=1

Collect 2–3 minutes of systemd FastAPI logs containing CAREWAVE_BATCH_TIMELINE,
plus ESP32 serial send/ack results. Never paste passwords or tokens.

Every JSON diagnostic includes:
- server batch received_at and time between received batches
- first_frame_id, last_frame_id, previous_last_frame_id, frame_gap_count
- candidate_start, previous_next_start, drift_seconds
- reason such as FRAME_CONTINUOUS_BUT_DRIFT_REBASE
- actual assigned DB start/end, number of radar frames, DB insert time in ms.

Diagnosis:
- Continuous frame IDs + DRIFT_REBASE => timestamp assignment jumped even though adjacent batches' radar sequence was contiguous.
- frame_gap_count greater than zero => UART or ESP32 transmission/queue loss is possible.
- large receive interval => delayed HTTP batches; confirm firmware behavior.
- large DB insert time => server or NCP MySQL latency may be adding backpressure.

Do not simply eliminate the three-second rebase condition: if one HTTP
batch requires about 1.17s in real time, blindly assigning exactly one fake
second per batch drifts away from real wall-clock time. We must first inspect
ESP32 firmware for radar frame cadence and send timestamps, then group
observations into real 1-second bins.

Second issue: presence=1 with missing X/Y/Z can mean maintained occupancy,
not verified stillness. Display may carry prior coordinates with an explicit
stale/estimated flag; movement, fall and inactivity detectors must NOT treat
unknown speed as a measured zero.
