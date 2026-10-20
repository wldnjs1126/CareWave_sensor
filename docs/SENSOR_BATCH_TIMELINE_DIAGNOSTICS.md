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

## v5.0.5 firmware retest: 2026-10-20

- Early Wi-Fi outage: 21 batches dropped before HTTP, 20 frames/observations each. This is genuine untransmitted data.
- After recovery: 85 consecutive HTTP 200 responses, radar frame IDs 421 through 2146 continuous (1,726 frames), no reported frame gaps.
- Median HTTP response 66 ms, mean 83.5 ms. Mean ESP32 batch build elapsed 1,030 ms.
- Timestamp gap #1: server window_end 17:20:01 then next window_start 17:20:05; radar frame IDs 993 -> 994 continuous.
- Timestamp gap #2: server window_end 17:20:40 then next window_start 17:20:44; radar frame IDs 1702 -> 1703 continuous.
- These demonstrate 4-second DB window label holes despite continuous radar frames successfully delivered by HTTP.
- Backend assignment REASON is not yet proven: obtain the opt-in server CAREWAVE_BATCH_TIMELINE log before changing the production window assignment.
- Next check: compare the reason, drift_seconds, frame_gap_count, previous_last_frame_id, and assigned_start values for both gaps.
- Never synthesize four missing seconds or write zero velocity. Never simply disable rebasing without measuring accumulated timestamp drift.
- Separately, add a bounded ESP32 offline queue/retry; retain real sample acquisition time to avoid relabeling old records as current.

## Experimental firmware A/B: v5.0.6 frame-paced diagnostic

An Arduino diagnostic firmware ZIP has been prepared as a separate user artifact (not deployed). The original v5.0.5 sketch is retained.

- Based on radar configuration frameCfg 55.00ms, build batches from a cumulative frame clock: add 55ms for each parsed frame; send when total reaches 1000ms; keep the modulo-1000 remainder.
- This yields roughly 18 or 19 radar frames per 1-second batch instead of v5.0.5 millis()-triggered 20-frame (~1.10 second) batches.
- Simulated with 1,800 continuous frames: 99 complete nominal second-bins (81 batches of 18, 18 batches of 19), 0 nominal accumulated remainder.
- During Wi-Fi outage batches are **still dropped**; HTTP still blocks UART and no backlog guarantee is provided. Firmware is a controlled A/B prototype only, not a production fix.
- Running test: copy working private carewave_secrets.h settings, upload diagnostic sketch in Arduino IDE and collect 2–3 minutes of HTTP 200 and DIAG_BATCH logs. Verify 18/19 frames/batch and continuous frame numbers.
- Compare SQL sensor_raw.window_start with created_at over matching test interval. If 4-second gaps remain, collect server CAREWAVE_BATCH_TIMELINE entries and implement true frame-acquisition-time 1-second server aggregation rather than artificial continuity.
- Do not alter life_event or synthesize missing sensor data while testing.

## v5.0.6 frame-paced test: October 20, 2026, 17:55:53–17:58:17 KST

- User's 144 ESP32 DIAG_BATCH records contain 143 HTTP 200 and one HTTP -11 (59th batch, frames 1056 through 1073).
- 18-frame batches: 117; 19-frame batches: 27. First-to-last radar frame IDs 1 through 2619 have no discontinuities; frame_gaps_total remains 0.
- Median HTTP processing time is 62ms; average batch-build elapsed around 919ms; max UART backlog 1376 bytes.
- For the 143 successful HTTP acknowledgements, **there were NO four-second jumps**. A one-second interval (17:56:51 to 17:56:52) lies between successful ACK window labels, corresponding to the batch whose HTTP response failed.
- IMPORTANT: HTTP -11 only means the ESP32 failed to obtain a valid response (often HTTPClient read timeout). It DOES NOT prove the server failed to COMMIT the missing batch. Inspect actual sensor_raw at 17:56:51 with a read-only query before treating it as missing.
- Do not retry blindly yet: server currently has no durable batch idempotency key / UNIQUE constraint on sensor/sensor-run/frame-range. After response timeout, retrying may insert a duplicate DB window.
- To distinguish actual DB loss from an acknowledgement timeout, run on CareWave_AI branch: python -m scripts.diagnose_sensor_timeline --subject-id 1 --sensor-id 1 --since "2026-10-20 17:55:50" --until "2026-10-20 17:58:20"
- Next permanent transport improvement: retry with bounded queue and a server-generated idempotent insert keyed to sensor identity + acquisition session + batch frame range. Ensure the radar restarts and resets frame_id between sessions without collisions.
- Avoid treating a missing ACK as confirmed packet loss and avoid synthesizing missing sensor frames.
