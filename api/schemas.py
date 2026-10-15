from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RadarFrameIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Final DB uses VARCHAR IDs, but numeric IDs are accepted for current ESP32 compatibility.
    sensor_id: str | int
    subject_id: str | int | None = None

    # One radar frame can contain multiple target observations.
    frame_id: int | None = None
    target_id: int | None = None

    x: float | None = None
    y: float | None = None
    z: float | None = None

    velocity_x: float | None = None
    velocity_y: float | None = None
    velocity_z: float | None = None

    acceleration_x: float | None = None
    acceleration_y: float | None = None
    acceleration_z: float | None = None

    doppler: float | None = None
    speed: float | None = None
    height: float | None = None
    movement_level: float | None = None
    zone: str | None = None

    point_count: int | None = None
    snr: float | None = None
    presence: bool = False

    timestamp: datetime | None = None


class RadarFrameBatchIn(BaseModel):
    # Around 18-20 frames/sec can contain several TIDs per frame,
    # so the batch limit must be larger than the frame count itself.
    frames: list[RadarFrameIn] = Field(min_length=1, max_length=256)
