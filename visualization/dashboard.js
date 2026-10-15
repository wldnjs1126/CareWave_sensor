const SENSOR_ID = "1";

// Radar coordinate mapping for the current room view.
// X: -2 m ~ +2 m
// Y:  0 m ~ 5 m
const ROOM_X_MIN = -2.0;
const ROOM_X_MAX = 2.0;
const ROOM_Y_MIN = 0.0;
const ROOM_Y_MAX = 5.0;


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


function hideTarget() {
    target.classList.add("hidden");

    waitingMessage.classList.remove(
        "hidden"
    );

    waitingMessage.textContent =
        "감지된 Target 없음";

    presence.textContent = "NO";
    targetId.textContent = "-";
    xValue.textContent = "-";
    yValue.textContent = "-";
    zValue.textContent = "-";
    speedValue.textContent = "-";
    heightValue.textContent = "-";
}


function showTarget(data) {
    const targets =
        Array.isArray(data.targets)
            ? data.targets
            : [];

    if (
        !data.presence ||
        targets.length === 0
    ) {
        hideTarget();
        return;
    }

    // Current CareWave filtering is calibrated for
    // the one-person room scenario, so display
    // the first valid target.
    const current = targets[0];

    const x = Number(current.x);
    const y = Number(current.y);

    if (
        !Number.isFinite(x) ||
        !Number.isFinite(y)
    ) {
        hideTarget();
        return;
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

    const topPercent =
        clamp(
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
        current.target_id ?? "1";

    target.classList.remove("hidden");

    waitingMessage.classList.add(
        "hidden"
    );

    presence.textContent = "YES";

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

    frameId.textContent =
        data.frame_id ?? frameId.textContent;
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
                    showTarget(data);
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
            target.classList.add("hidden");

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
