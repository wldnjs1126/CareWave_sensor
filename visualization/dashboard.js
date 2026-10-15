const SENSOR_ID = "1";


const onlineDot =
    document.getElementById(
        "onlineDot"
    );

const onlineText =
    document.getElementById(
        "onlineText"
    );

const radarState =
    document.getElementById(
        "radarState"
    );

const frameId =
    document.getElementById(
        "frameId"
    );

const lastSeen =
    document.getElementById(
        "lastSeen"
    );

const systemMessage =
    document.getElementById(
        "systemMessage"
    );


const startButton =
    document.getElementById(
        "startButton"
    );

const stopButton =
    document.getElementById(
        "stopButton"
    );

const restartButton =
    document.getElementById(
        "restartButton"
    );


function setMessage(message) {

    systemMessage.textContent =
        message;
}


function setButtonsDisabled(
    disabled
) {

    startButton.disabled =
        disabled;

    stopButton.disabled =
        disabled;

    restartButton.disabled =
        disabled;
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


        frameId.textContent =
            data.frame_id ?? "-";


        if (data.last_seen) {

            const date =
                new Date(
                    data.last_seen
                );

            lastSeen.textContent =
                date.toLocaleTimeString(
                    "ko-KR"
                );

        } else {

            lastSeen.textContent =
                "-";
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


async function sendCommand(
    command
) {

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
                setButtonsDisabled(
                    false
                );
            },
            1000
        );
    }
}


startButton.addEventListener(
    "click",
    () => sendCommand(
        "START"
    )
);


stopButton.addEventListener(
    "click",
    () => sendCommand(
        "STOP"
    )
);


restartButton.addEventListener(
    "click",
    () => sendCommand(
        "RESTART"
    )
);


loadStatus();


setInterval(
    loadStatus,
    2000
);