const SENSOR_ID = "1";

/*
Room coordinate system

Physical room:
- width: 3.6 m
- depth: 3.8 m

Radar:
- bottom-center
- height: approximately 0.75 m

Room bounds:
- X = -1.8 ... +1.8 m
- Y =  0.0 ...  3.8 m
*/
const ROOM_X_MIN = -1.8;
const ROOM_X_MAX = 1.8;
const ROOM_Y_MIN = 0.0;
const ROOM_Y_MAX = 3.8;

// Display-only filtering. Raw sensor values, DB data and fall detection are
// NEVER changed by this logic.
const DISPLAY_EMA_ALPHA = 0.60;
const DISPLAY_ASSOCIATION_RADIUS_M = 1.5;
const DISPLAY_TRACK_TTL_MS = 3000;
const DISPLAY_MAX_STEP_MPS = 2.0;

let displayTrack = null; // {x, y, targetId, measuredAt}
let lastFastLiveAt = 0;

function resetDisplayTrack() {
    displayTrack = null;
}

function validCoordinate(value) {
    return value !== null &&
        value !== undefined &&
        value !== "" &&
        Number.isFinite(Number(value));
}

function select2DTarget(targets) {
    const valid = targets.filter(isInsidePhysicalRoom);
    if (!valid.length) return null;

    const now = Date.now();
    if (
        !displayTrack ||
        now - displayTrack.measuredAt > DISPLAY_TRACK_TTL_MS
    ) {
        return valid[0];
    }

    // Do not jump to the first arbitrary radar track when it changes order.
    const sameId = valid.find(
        item =>
            item.target_id != null &&
            displayTrack.targetId != null &&
            String(item.target_id) === String(displayTrack.targetId)
    );
    if (sameId) return sameId;

    // Reassociate within a plausible distance when TI changes the TID.
    let nearest = null;
    let nearestDistance = Infinity;
    for (const item of valid) {
        const distance = Math.hypot(
            Number(item.x) - displayTrack.x,
            Number(item.y) - displayTrack.y,
        );
        if (distance < nearestDistance) {
            nearestDistance = distance;
            nearest = item;
        }
    }
    return nearestDistance <= DISPLAY_ASSOCIATION_RADIUS_M
        ? nearest : null;
}


const onlineDot =
    document.getElementById("onlineDot");

const onlineText =
    document.getElementById("onlineText");

const radarState =
    document.getElementById("radarState");

const frameId =
    document.getElementById("frameId");

const lastSeen =
    document.getElementById("lastSeen");

const systemMessage =
    document.getElementById("systemMessage");

const startButton =
    document.getElementById("startButton");

const stopButton =
    document.getElementById("stopButton");

const restartButton =
    document.getElementById("restartButton");

const target =
    document.getElementById("target");

const waitingMessage =
    document.getElementById("waitingMessage");

const presence =
    document.getElementById("presence");

const instantDetection =
    document.getElementById("instantDetection");

const occupancyState =
    document.getElementById("occupancyState");

const zoneValue =
    document.getElementById("zoneValue");

const targetId =
    document.getElementById("targetId");

const xValue =
    document.getElementById("xValue");

const yValue =
    document.getElementById("yValue");

const zValue =
    document.getElementById("zValue");

const speedValue =
    document.getElementById("speedValue");

const heightValue =
    document.getElementById("heightValue");

const movementState =
    document.getElementById("movementState");

// Current speed observation, for UI display ONLY.
// The 3-second MOVEMENT life-event condition belongs to the event engine.
const MOVEMENT_DISPLAY_SPEED_MIN = 0.10;

function showMovementObservation(speed, kind = "measured") {
    if (!movementState) return;
    if (kind === "absent") {
        movementState.textContent = "부재";
        return;
    }
    if (kind === "inferred") {
        movementState.textContent = "미검출 · 재실 추정";
        return;
    }
    if (speed === null || speed === undefined ||
        speed === "" || !Number.isFinite(Number(speed)) ||
        Number(speed) < 0) {
        movementState.textContent = "속도 측정 대기";
        return;
    }
    movementState.textContent = Number(speed) >= MOVEMENT_DISPLAY_SPEED_MIN
        ? "움직임 관측"
        : "저속 관측";
}


function setMessage(message) {
    systemMessage.textContent = message;
}


function setButtonsDisabled(disabled) {
    startButton.disabled = disabled;
    stopButton.disabled = disabled;
    restartButton.disabled = disabled;
}


function formatMeters(value) {
    if (
        value === null ||
        value === undefined
    ) {
        return "-";
    }

    return `${Number(value).toFixed(2)} m`;
}


function clamp(value, min, max) {
    return Math.min(
        Math.max(value, min),
        max
    );
}


function isInsidePhysicalRoom(position) {
    if (!position) {
        return false;
    }

    if (!validCoordinate(position.x) || !validCoordinate(position.y)) {
        return false;
    }
    const x = Number(position.x);
    const y = Number(position.y);

    return (
        Number.isFinite(x) &&
        Number.isFinite(y) &&
        x >= ROOM_X_MIN &&
        x <= ROOM_X_MAX &&
        y >= ROOM_Y_MIN &&
        y <= ROOM_Y_MAX
    );
}


function placeTarget(position, inferred) {
    if (!isInsidePhysicalRoom(position)) return false;

    const now = Date.now();
    const measuredX = Number(position.x);
    const measuredY = Number(position.y);
    let x = measuredX;
    let y = measuredY;

    if (displayTrack) {
        if (inferred) {
            // Inference means no current measured position. Keep the last
            // plotted position without claiming a fresh measurement.
            x = displayTrack.x;
            y = displayTrack.y;
        } else {
            const elapsedMs = now - displayTrack.measuredAt;
            if (elapsedMs >= 0 && elapsedMs < DISPLAY_TRACK_TTL_MS) {
                const deltaX = measuredX - displayTrack.x;
                const deltaY = measuredY - displayTrack.y;
                const distance = Math.hypot(deltaX, deltaY);
                // Only the visual marker is capped, not the raw measurements.
                const maxStep = DISPLAY_MAX_STEP_MPS *
                    Math.max(elapsedMs / 1000, 0.25);
                const portion = distance > 0
                    ? Math.min(1, maxStep / distance) : 1;
                x = displayTrack.x +
                    deltaX * portion * DISPLAY_EMA_ALPHA;
                y = displayTrack.y +
                    deltaY * portion * DISPLAY_EMA_ALPHA;
            }
        }
    }

    displayTrack = {
        x, y,
        targetId: inferred
            ? (displayTrack?.targetId ?? position.target_id ?? null)
            : (position.target_id ?? null),
        measuredAt: inferred
            ? (displayTrack?.measuredAt ?? 0)
            : now,
    };

    const leftPercent = clamp(
        ((x - ROOM_X_MIN) / (ROOM_X_MAX - ROOM_X_MIN)) * 100,
        1, 99
    );
    const topPercent = clamp(
        100 - ((y - ROOM_Y_MIN) / (ROOM_Y_MAX - ROOM_Y_MIN)) * 100,
        1, 99
    );

    target.style.left = `${leftPercent}%`;
    target.style.top = `${topPercent}%`;
    target.textContent = inferred ? "~" : (position.target_id ?? "1");
    target.className = inferred ? "target inferred" : "target";
    return true;
}

function showAbsent(data) {
    resetDisplayTrack();
    showMovementObservation(null, "absent");
    target.classList.add("hidden");

    waitingMessage.classList.remove(
        "hidden"
    );

    waitingMessage.textContent =
        "부재 / Target 없음";

    presence.textContent = "NO";
    instantDetection.textContent = "NO";

    occupancyState.textContent =
        data.occupancy_state ?? "ABSENT";

    zoneValue.textContent =
        data.zone ?? "-";

    targetId.textContent = "-";
    xValue.textContent = "-";
    yValue.textContent = "-";
    zValue.textContent = "-";
    speedValue.textContent = "-";
    heightValue.textContent = "-";
}


function showLiveData(data) {
    const targets =
        Array.isArray(data.targets)
            ? data.targets
            : [];

    const detected =
        Boolean(data.detected) &&
        targets.length > 0;

    const current = detected ? select2DTarget(targets) : null;
    const occupied =
        Boolean(data.presence);

    presence.textContent =
        occupied ? "YES" : "NO";

    instantDetection.textContent =
        current ? "YES" : "NO";

    occupancyState.textContent =
        data.occupancy_state ?? "-";

    zoneValue.textContent =
        data.zone ?? "-";

    frameId.textContent =
        data.frame_id ??
        frameId.textContent;


    // --------------------------------------------------------
    // 1. Live radar target exists now
    // --------------------------------------------------------
    // The fast stream wins for 2D while it is fresh. A slow batch
    // arriving later must not drag the marker back to an old position.
    if (current && Date.now() - lastFastLiveAt < 1500) {
        return;
    }
    if (current) {
        const placed =
            placeTarget(
                current,
                false
            );

        if (!placed) {
            // A rejected position is not proof that the room is empty.
            return;
        }

        waitingMessage.classList.add(
            "hidden"
        );

        targetId.textContent =
            current.target_id ?? "-";

        xValue.textContent =
            formatMeters(current.x);

        yValue.textContent =
            formatMeters(current.y);

        zValue.textContent =
            formatMeters(current.z);

        speedValue.textContent =
            current.speed == null
                ? "-"
                : (
                    `${Number(
                        current.speed
                    ).toFixed(2)} m/s`
                );

        heightValue.textContent =
            formatMeters(
                current.height
            );

        showMovementObservation(current.speed);
        return;
    }


    // --------------------------------------------------------
    // 2. No instant target, but CareWave still knows the
    //    subject has not left the room.
    // --------------------------------------------------------
    if (occupied) {
        showMovementObservation(null, "inferred");
        const last =
            data.last_known_position;

        if (
            last &&
            placeTarget(
                last,
                true
            )
        ) {
            waitingMessage.classList.add(
                "hidden"
            );

            targetId.textContent =
                last.target_id ?? "-";

            xValue.textContent =
                formatMeters(last.x);

            yValue.textContent =
                formatMeters(last.y);

            zValue.textContent =
                formatMeters(last.z);

            // Do not invent a measured zero speed.
            speedValue.textContent =
                "미검출 · 정지 추정";

            heightValue.textContent =
                "-";

        } else {
            target.classList.add(
                "hidden"
            );

            waitingMessage.classList.remove(
                "hidden"
            );

            waitingMessage.textContent =
                "재실 추정 · 위치 갱신 대기";
        }

        return;
    }


    // --------------------------------------------------------
    // 3. Absence
    // --------------------------------------------------------
    showAbsent(data);
}


function showFastLiveData(data) {
    frameId.textContent =
        data.frame_id ??
        frameId.textContent;

    const targets =
        Array.isArray(data.targets)
            ? data.targets
            : [];

    // Only use a fast target for the 2D person marker when it is physically
    // inside the test room. OUTSIDE/stale tracks are still available to the
    // 3D point-cloud view but cannot create a fake room target here.
    lastFastLiveAt = Date.now();
    const current = select2DTarget(targets);

    if (!current) {
        instantDetection.textContent = "NO";

        window.dispatchEvent(
            new CustomEvent(
                "carewave:fast-live",
                { detail: data }
            )
        );

        return;
    }

    instantDetection.textContent = "YES";

    placeTarget(
        current,
        false
    );

    waitingMessage.classList.add(
        "hidden"
    );

    targetId.textContent =
        current.target_id ?? "-";

    xValue.textContent =
        formatMeters(current.x);

    yValue.textContent =
        formatMeters(current.y);

    zValue.textContent =
        formatMeters(current.z);

    speedValue.textContent =
        current.speed == null
            ? "-"
            : `${Number(current.speed).toFixed(2)} m/s`;

    heightValue.textContent =
        formatMeters(current.height);
    showMovementObservation(current.speed);

    window.dispatchEvent(
        new CustomEvent(
            "carewave:fast-live",
            { detail: data }
        )
    );
}


async function loadStatus() {
    try {
        const response =
            await fetch(
                `/api/sensor/${SENSOR_ID}/status`
            );

        if (!response.ok) {
            throw new Error(
                `HTTP ${response.status}`
            );
        }

        const data =
            await response.json();

        if (data.online) {
            onlineDot.className =
                "dot online";

            onlineText.textContent =
                "ONLINE";
        } else {
            onlineDot.className =
                "dot offline";

            onlineText.textContent =
                "OFFLINE";
        }

        radarState.textContent =
            data.state ?? "UNKNOWN";

        if (!data.online || data.state === "STOPPED" ||
            data.state === "ERROR") {
            if (movementState) {
                movementState.textContent =
                    data.online ? "센서 정지" : "수신 없음";
            }
            resetDisplayTrack();
            lastFastLiveAt = 0;
            target.classList.add("hidden");
        }

        if (data.frame_id != null) {
            frameId.textContent =
                data.frame_id;
        }

        if (data.last_seen) {
            const date =
                new Date(data.last_seen);

            lastSeen.textContent =
                date.toLocaleTimeString(
                    "ko-KR"
                );
        } else {
            lastSeen.textContent = "-";
        }

        if (data.online) {
            setMessage(
                `Sensor ${data.state}`
            );
        } else {
            setMessage(
                "Sensor connection unavailable"
            );
        }

    } catch (error) {
        onlineDot.className =
            "dot offline";

        onlineText.textContent =
            "OFFLINE";

        radarState.textContent =
            "UNKNOWN";
        if (movementState) movementState.textContent = "연결 오류";
        resetDisplayTrack();
        lastFastLiveAt = 0;
        target.classList.add("hidden");

        setMessage(
            "API connection failed"
        );

        console.error(error);
    }
}


async function sendCommand(command) {
    setButtonsDisabled(true);

    setMessage(
        `${command} command sending...`
    );

    try {
        const response =
            await fetch(
                `/api/sensor/${SENSOR_ID}/command`,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            command: command
                        })
                }
            );

        if (!response.ok) {
            throw new Error(
                `HTTP ${response.status}`
            );
        }

        const data =
            await response.json();

        setMessage(
            `${data.command} command queued`
        );

        setTimeout(
            loadStatus,
            1200
        );

    } catch (error) {
        setMessage(
            `${command} command failed`
        );

        console.error(error);

    } finally {
        setTimeout(
            () => {
                setButtonsDisabled(false);
            },
            1000
        );
    }
}


function connectLiveWebSocket() {
    const protocol =
        window.location.protocol === "https:"
            ? "wss:"
            : "ws:";

    const url =
        `${protocol}//${window.location.host}` +
        `/ws/sensor/${SENSOR_ID}`;

    const socket =
        new WebSocket(url);

    socket.addEventListener(
        "open",
        () => {
            waitingMessage.textContent =
                "Target 감지 대기 중";

            setMessage(
                "Live radar connected"
            );
        }
    );

    socket.addEventListener(
        "message",
        (event) => {
            try {
                const data =
                    JSON.parse(event.data);

                if (
                    data.type ===
                    "radar_live"
                ) {
                    showLiveData(data);
                }
                else if (
                    data.type ===
                    "radar_fast_live"
                ) {
                    showFastLiveData(data);
                }

            } catch (error) {
                console.error(
                    "Live data parse error",
                    error
                );
            }
        }
    );

    socket.addEventListener(
        "close",
        () => {
            target.classList.add(
                "hidden"
            );

            waitingMessage.classList.remove(
                "hidden"
            );

            waitingMessage.textContent =
                "실시간 연결 재시도 중...";

            setTimeout(
                connectLiveWebSocket,
                2000
            );
        }
    );

    socket.addEventListener(
        "error",
        () => {
            socket.close();
        }
    );
}


startButton.addEventListener(
    "click",
    () => sendCommand("START")
);

stopButton.addEventListener(
    "click",
    () => sendCommand("STOP")
);

restartButton.addEventListener(
    "click",
    () => sendCommand("RESTART")
);


loadStatus();

setInterval(
    loadStatus,
    2000
);

connectLiveWebSocket();
