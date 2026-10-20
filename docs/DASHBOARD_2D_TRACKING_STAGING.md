# CareWave 2D dashboard location stability (diagnostic-only)

Scope: only `visualization/dashboard.js` and optional no-network Node.js test. No modification to `sensor_raw`, server event/risk calculations, ESP32, `.env`, or NCP service.

## What changed
- Prefer an existing target ID when the radar target array changes order.
- Associate a new target ID only when near the recent previous displayed position.
- Reject NULL/empty coordinates and locations outside **the existing test-room coordinate bounds**.
- Smooth only the 2D plotted marker. Numeric X/Y/Z readouts remain the raw measured values.
- Keep fresh fast-live frames from being overwritten by a late 1-second radar batch when stage 2 is eventually enabled.
- Hide stale markers when the server reports STOPPED/OFFLINE.
- This is not a validated tracking or fall-detection algorithm.

## IMPORTANT geometry check before any deployment
The checked-in dashboard still models the **current test room** as 3.6m wide x 3.8m deep, radar at bottom-center, radar height approximately 0.75m. The eventual CareWave installation may instead be a hospital room with a centered ceiling radar. Do not change the backend, zones or UI map to a different room geometry without confirming the actual mounting/orientation and measured radar coordinates.

## Local smoke test
From the separate `C:\CareWave_sensor_reliable_test` diagnostic checkout:
```cmd
git status --short
git pull --ff-only
python -m unittest discover -s tests -v
```
Expected backend 5 tests pass. If Node.js is already installed, optional:
```cmd
node --test tests\dashboard2d_tracking.test.cjs
```
Expected 5 dashboard smoke checks. Do not install Node.js just for this step if it isn't needed.

**Pulling the diagnostic branch on Windows does not update the running NCP dashboard.** Deployment to the actual dashboard host is a separate operation only after checking the user's actual service deployment path, reviewing local uncommitted files, and confirming the target is staging or a deliberately approved production update.

## What this does not prove
- No live radar points were used to validate the tracking decisions.
- No actual room-layout calibration has been performed.
- Stage 1 deliberately does not emit /api/sensor/live; a 3D point cloud cannot appear until stage 2 is safely re-enabled.
