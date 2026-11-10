"""Transform TI raw 3D measurements into the room coordinate system.

Important: matrix in room_config.json is UNCALIBRATED. No physical claim about
board-axis orientation is possible from room photos alone. Validate it first.
"""
from __future__ import annotations
from typing import Any
import room_geometry as g

def vector_to_room(x: float, y: float, z: float) -> tuple[float, float, float]:
    v = float(x), float(y), float(z)
    return tuple(sum(row[i] * v[i] for i in range(3)) for row in g.ROTATION)

def point_to_room(x: float, y: float, z: float) -> tuple[float, float, float]:
    a, b, c = vector_to_room(x, y, z)
    tx, ty, tz = g.SENSOR_POSITION
    return a + tx, b + ty, c + tz

def frame_to_room(frame: Any):
    """Convert Pydantic model, preserving magnitude-based speed and TI height."""
    update = {}
    pos = frame.x, frame.y, frame.z
    if all(v is not None for v in pos):
        update.update(zip(("x", "y", "z"), point_to_room(*pos)))
    else:
        update.update(x=None, y=None, z=None)
    for fields in (("velocity_x", "velocity_y", "velocity_z"),
                   ("acceleration_x", "acceleration_y", "acceleration_z")):
        raw = tuple(getattr(frame, field) for field in fields)
        if all(v is not None for v in raw):
            update.update(zip(fields, vector_to_room(*raw)))
        else:
            update.update({field: None for field in fields})
    return frame.model_copy(update=update)

def fast_live_to_room(live: Any):
    targets = []
    for item in live.targets:
        a = list(item)
        if len(a) < 4 or not all(v is not None for v in a[1:4]):
            continue
        a[1:4] = list(point_to_room(*a[1:4]))
        targets.append(a)
    points = []
    for item in live.points:
        a = list(item)
        if len(a) < 3 or not all(v is not None for v in a[:3]):
            continue
        a[:3] = list(point_to_room(*a[:3]))
        points.append(a)
    return live.model_copy(update={"targets": targets, "points": points})
