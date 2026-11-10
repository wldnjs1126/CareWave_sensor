"""Grounded room geometry for CareWave's 2026-11 ceiling-mounted pilot.

The room is a RECTANGLE. A wardrobe is simply the +Y WALL, not a depth.
Positions are measured in meters relative to the sensor's floor projection:
X left (-)/right (+), Y bathroom wall (-)/wardrobe wall (+), Z floor up.
"""
from __future__ import annotations
import json
from pathlib import Path

CONFIG = json.loads((Path(__file__).resolve().parent / "room_config.json").read_text(encoding="utf-8"))
R = CONFIG["room"]
B = CONFIG["bed"]
E = CONFIG["entrance"]
T = CONFIG["bathroom"]
S = CONFIG["sensor"]
ROOM_X_MIN = -R["width_x_m"] / 2
ROOM_X_MAX = R["width_x_m"] / 2
ROOM_Y_MIN = -R["length_y_m"] / 2
ROOM_Y_MAX = R["length_y_m"] / 2

BED_X_MIN = ROOM_X_MIN + B["gap_from_left_wall_m"]
BED_X_MAX = BED_X_MIN + B["width_along_x_m"]
BED_Y_MAX = ROOM_Y_MAX - B["gap_from_top_wall_m"]
BED_Y_MIN = BED_Y_MAX - B["length_along_y_m"]
BED_HEIGHT = B["height_m"]

# Entrance: starts at the bottom-left corner and runs up the left wall.
EXIT_X_MIN = ROOM_X_MIN
EXIT_X_MAX = ROOM_X_MIN + E["inside_zone_depth_m"]
EXIT_Y_MIN = ROOM_Y_MIN
EXIT_Y_MAX = ROOM_Y_MIN + E["opening_length_m"]
EXIT_APPROACH_X_MIN = EXIT_X_MIN
EXIT_APPROACH_X_MAX = min(ROOM_X_MAX, EXIT_X_MAX + E["approach_extra_depth_m"])
EXIT_APPROACH_Y_MIN = EXIT_Y_MIN
EXIT_APPROACH_Y_MAX = min(ROOM_Y_MAX, EXIT_Y_MAX + E["approach_extra_length_m"])

# Bathroom: marked on bottom wall, 40 cm from LEFT wall, width 50 cm.
BATHROOM_X_MIN = ROOM_X_MIN + T["distance_from_left_wall_m"]
BATHROOM_X_MAX = BATHROOM_X_MIN + T["opening_width_m"]
BATHROOM_Y_MIN = ROOM_Y_MIN
BATHROOM_Y_MAX = ROOM_Y_MIN + T["inside_zone_depth_m"]

SENSOR_HEIGHT = R["ceiling_height_m"]
SENSOR_POSITION = tuple(float(v) for v in S["position_room_xyz_m"])
ROTATION = tuple(tuple(map(float, row)) for row in S["raw_to_room_rotation"])

def validate() -> None:
    assert R["width_x_m"] > 0 and R["length_y_m"] > 0 and SENSOR_HEIGHT > 0
    assert ROOM_X_MIN <= BED_X_MIN < BED_X_MAX <= ROOM_X_MAX + 1e-9
    assert ROOM_Y_MIN <= BED_Y_MIN < BED_Y_MAX <= ROOM_Y_MAX + 1e-9
    assert ROOM_X_MIN <= EXIT_X_MIN < EXIT_X_MAX <= ROOM_X_MAX
    assert ROOM_Y_MIN <= EXIT_Y_MIN < EXIT_Y_MAX <= ROOM_Y_MAX
    assert ROOM_X_MIN <= BATHROOM_X_MIN < BATHROOM_X_MAX <= ROOM_X_MAX
    assert ROOM_Y_MIN <= BATHROOM_Y_MIN < BATHROOM_Y_MAX <= ROOM_Y_MAX
    assert len(ROTATION) == 3 and all(len(row) == 3 for row in ROTATION)
    for i in range(3):
        assert abs(sum(n*n for n in ROTATION[i]) - 1) < 1e-6
        for j in range(i):
            assert abs(sum(ROTATION[i][k]*ROTATION[j][k] for k in range(3))) < 1e-6

validate()

def zone(x: float | None, y: float | None) -> str | None:
    if x is None or y is None:
        return None
    if BED_X_MIN <= x <= BED_X_MAX and BED_Y_MIN <= y <= BED_Y_MAX:
        return "BED"
    if BATHROOM_X_MIN <= x <= BATHROOM_X_MAX and BATHROOM_Y_MIN <= y <= BATHROOM_Y_MAX:
        return "BATHROOM"
    if EXIT_X_MIN <= x <= EXIT_X_MAX and EXIT_Y_MIN <= y <= EXIT_Y_MAX:
        return "EXIT"
    if ROOM_X_MIN <= x <= ROOM_X_MAX and ROOM_Y_MIN <= y <= ROOM_Y_MAX:
        return "ROOM"
    return "OUTSIDE"

def browser_dict() -> dict:
    return {
        "room": {"xmin":ROOM_X_MIN,"xmax":ROOM_X_MAX,"ymin":ROOM_Y_MIN,"ymax":ROOM_Y_MAX},
        "bed": {"xmin":BED_X_MIN,"xmax":BED_X_MAX,"ymin":BED_Y_MIN,"ymax":BED_Y_MAX,"height":BED_HEIGHT},
        "entrance": {"xmin":EXIT_X_MIN,"xmax":EXIT_X_MAX,"ymin":EXIT_Y_MIN,"ymax":EXIT_Y_MAX},
        "bathroom": {"xmin":BATHROOM_X_MIN,"xmax":BATHROOM_X_MAX,"ymin":BATHROOM_Y_MIN,"ymax":BATHROOM_Y_MAX},
        "sensor": {"height":SENSOR_HEIGHT},
    }

if __name__ == "__main__":
    for key in ("ROOM_X_MIN","ROOM_X_MAX","ROOM_Y_MIN","ROOM_Y_MAX","BED_X_MIN","BED_X_MAX","BED_Y_MIN","BED_Y_MAX","EXIT_X_MIN","EXIT_X_MAX","EXIT_Y_MIN","EXIT_Y_MAX","BATHROOM_X_MIN","BATHROOM_X_MAX","BATHROOM_Y_MIN","BATHROOM_Y_MAX"):
        print(f"{key:27s} {globals()[key]:+.3f} m")
    print("Sensor", SENSOR_POSITION)
    print("Rotation calibrated:", S["rotation_is_calibrated"])
