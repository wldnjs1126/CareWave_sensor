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


function placeTarget(
    position,
    inferred
) {
    const x = Number(position.x);
    const y = Number(position.y);

    if (
        !Number.isFinite(x) ||
        !Number.isFinite(y)
    ) {
        return false;
    }

    const leftPercent =
        clamp(
            (
                (x - ROOM_X_MIN) /
                (ROOM_X_MAX - ROOM_X_MIN)
            ) * 100,
            1,
            99
        );

    // Radar Y grows toward the top wall.
    const topPercent =
        clamp(
            100 -
            (
                (y - ROOM_Y_MIN) /
                (ROOM_Y_MAX - ROOM_Y_MIN)
            ) * 100,
            1,
            99
        );

    target.style.left =
        `${leftPercent}%`;

    target.style.top =
        `${topPercent}%`;

    target.textContent =
        inferred
            ? "~"
            : (
                position.target_id ??
                "1"
            );

    target.className =
        inferred
            ? "target inferred"
            : "target";

    return true;
}


function showAbsent(data) {
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

    const occupied =
        Boolean(data.presence);

    presence.textContent =
        occupied ? "YES" : "NO";

    instantDetection.textContent =
        detected ? "YES" : "NO";

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
    if (detected) {
        const current = targets[0];

        const placed =
            placeTarget(
                current,
                false
            );

        if (!placed) {
            showAbsent(data);
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

        return;
    }


    // --------------------------------------------------------
    // 2. No instant target, but CareWave still knows the
    //    subject has not left the room.
    // --------------------------------------------------------
    if (occupied) {
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
    const current =
        targets.find(
            (item) =>
                isInsidePhysicalRoom(item)
        );

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
