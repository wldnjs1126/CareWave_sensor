from datetime import datetime
from itertools import count
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from pydantic import BaseModel


router = APIRouter(
    prefix="/api/sensor",
    tags=["sensor-control"],
)

KST = ZoneInfo("Asia/Seoul")

# --------------------------------------------------
# 메모리 저장소
# --------------------------------------------------

pending_commands: dict[str, dict] = {}
sensor_status: dict[str, dict] = {}

command_ids = count(1)


# --------------------------------------------------
# 요청 모델
# --------------------------------------------------

class CommandRequest(BaseModel):
    command: Literal[
        "START",
        "STOP",
        "RESTART",
    ]


class CommandAckRequest(BaseModel):
    command_id: int


class SensorStatusRequest(BaseModel):
    state: Literal[
        "BOOTING",
        "CONFIGURING",
        "RUNNING",
        "STOPPED",
        "RECOVERING",
        "ERROR",
    ]

    frame_id: int | None = None
    wifi_connected: bool | None = None


# --------------------------------------------------
# Dashboard → 서버
# 센서 명령 등록
# --------------------------------------------------

@router.post("/{sensor_id}/command")
def set_sensor_command(
    sensor_id: str,
    body: CommandRequest,
):
    command_id = next(command_ids)

    pending_commands[sensor_id] = {
        "command_id": command_id,
        "command": body.command,
        "created_at": datetime.now(KST),
    }

    return {
        "status": "queued",
        "sensor_id": sensor_id,
        "command_id": command_id,
        "command": body.command,
    }


# --------------------------------------------------
# ESP32 → 서버
# 실행할 명령 확인
# --------------------------------------------------

@router.get("/{sensor_id}/command")
def get_sensor_command(sensor_id: str):
    command = pending_commands.get(sensor_id)

    if command is None:
        return {
            "sensor_id": sensor_id,
            "command_id": None,
            "command": "NONE",
        }

    return {
        "sensor_id": sensor_id,
        "command_id": command["command_id"],
        "command": command["command"],
    }


# --------------------------------------------------
# ESP32 → 서버
# 명령 실행 완료 확인
# --------------------------------------------------

@router.post("/{sensor_id}/command/ack")
def acknowledge_sensor_command(
    sensor_id: str,
    body: CommandAckRequest,
):
    command = pending_commands.get(sensor_id)

    if command is None:
        return {
            "status": "already_cleared",
            "sensor_id": sensor_id,
        }

    if command["command_id"] != body.command_id:
        return {
            "status": "command_id_mismatch",
            "sensor_id": sensor_id,
        }

    del pending_commands[sensor_id]

    return {
        "status": "acknowledged",
        "sensor_id": sensor_id,
        "command_id": body.command_id,
    }


# --------------------------------------------------
# ESP32 → 서버
# 현재 상태 전송
# --------------------------------------------------

@router.post("/{sensor_id}/status")
def update_sensor_status(
    sensor_id: str,
    body: SensorStatusRequest,
):
    now = datetime.now(KST)

    sensor_status[sensor_id] = {
        "state": body.state,
        "frame_id": body.frame_id,
        "wifi_connected": body.wifi_connected,
        "last_seen": now,
    }

    return {
        "status": "updated",
        "sensor_id": sensor_id,
        "state": body.state,
    }


# --------------------------------------------------
# Dashboard → 서버
# 현재 센서 상태 확인
# --------------------------------------------------

@router.get("/{sensor_id}/status")
def get_sensor_status(sensor_id: str):
    status = sensor_status.get(sensor_id)

    if status is None:
        return {
            "sensor_id": sensor_id,
            "online": False,
            "state": "UNKNOWN",
            "frame_id": None,
            "wifi_connected": False,
            "last_seen": None,
        }

    now = datetime.now(KST)

    seconds_since_seen = (
        now - status["last_seen"]
    ).total_seconds()

    online = seconds_since_seen <= 10

    return {
        "sensor_id": sensor_id,
        "online": online,
        "state": status["state"],
        "frame_id": status["frame_id"],
        "wifi_connected": status["wifi_connected"],
        "last_seen": status["last_seen"].isoformat(),
    }