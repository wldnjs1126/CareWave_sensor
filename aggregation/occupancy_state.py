from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


# ============================================================
# Current CareWave test-room geometry
# ============================================================
#
# Dashboard / radar coordinates:
#   Radar origin: bottom-center of room
#   X: left (-) <---- 0 ----> right (+)
#   Y: radar (0) -----------> opposite wall (3.8 m)
#
# Room:
#   width  = 3.6 m  -> X = -1.8 .. +1.8
#   depth  = 3.8 m  -> Y =  0.0 ..  3.8
#
ROOM_X_MIN = -1.8
ROOM_X_MAX = 1.8
ROOM_Y_MIN = 0.0
ROOM_Y_MAX = 3.8

# Assumed bed:
# - horizontal
# - attached to left wall
# - 1.8 m x 1.0 m
# - upper wall gap about 1.2 m
#
# Top wall is Y=3.8.
# Therefore bed Y is approximately 1.6 .. 2.6.
BED_X_MIN = -1.8
BED_X_MAX = 0.0
BED_Y_MIN = 1.6
BED_Y_MAX = 2.6

# Assumed exit/door area is the upper-right part of the room.
# This is intentionally broader than the visual door itself so an exiting
# person can be recognized before the track disappears.
EXIT_X_MIN = 1.15
EXIT_Y_MIN = 2.70

# CareWave movement event threshold is 0.10 m/s.
# Use the same value to arm a door-exit candidate.
EXIT_SPEED_MIN = 0.10

# Absence rule after a confirmed moving target reaches the exit zone.
EXIT_CONFIRM_SECONDS = 10

# If a confirmed person becomes undetectable away from the door, do NOT
# immediately convert that to absence. This hold is long enough to support
# the 30-minute INACTIVITY event.
GENERAL_HOLD_SECONDS = 35 * 60

# If the last confirmed position was the bed and the subject was low-motion,
# keep room occupancy long enough for sleep monitoring.
BED_HOLD_SECONDS = 12 * 60 * 60


@dataclass
class OccupancyTrack:
    present: bool = False

    last_detection_at: datetime | None = None

    last_target_id: int | None = None
    last_x: float | None = None
    last_y: float | None = None
    last_z: float | None = None
    last_speed: float | None = None
    last_zone: str | None = None

    exit_armed: bool = False


class OccupancyManager:
    """
    Separates:
      1) instant radar target detection
      2) room occupancy state

    "No target this second" does NOT automatically mean "person left room".
    """

    def __init__(self):
        self._states: dict[
            tuple[str, str | None],
            OccupancyTrack,
        ] = {}

    @staticmethod
    def classify_zone(
        x: float | None,
        y: float | None,
    ) -> str | None:
        if x is None or y is None:
            return None

        if (
            BED_X_MIN <= x <= BED_X_MAX
            and BED_Y_MIN <= y <= BED_Y_MAX
        ):
            return "BED"

        if (
            x >= EXIT_X_MIN
            and y >= EXIT_Y_MIN
        ):
            return "EXIT"

        if (
            ROOM_X_MIN <= x <= ROOM_X_MAX
            and ROOM_Y_MIN <= y <= ROOM_Y_MAX
        ):
            return "ROOM"

        return "OUTSIDE"

    def _get_state(
        self,
        sensor_id,
        subject_id,
    ) -> OccupancyTrack:
        key = (
            str(sensor_id),
            None if subject_id is None else str(subject_id),
        )

        if key not in self._states:
            self._states[key] = OccupancyTrack()

        return self._states[key]

    def update(
        self,
        *,
        sensor_id,
        subject_id,
        detected: bool,
        now: datetime,
        target_id: int | None = None,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        speed: float | None = None,
    ) -> dict:
        state = self._get_state(
            sensor_id,
            subject_id,
        )

        # ----------------------------------------------------
        # A validated radar target exists now.
        # ----------------------------------------------------
        if detected:
            zone = self.classify_zone(x, y)

            state.present = True
            state.last_detection_at = now

            state.last_target_id = target_id
            state.last_x = x
            state.last_y = y
            state.last_z = z
            state.last_speed = speed
            state.last_zone = zone

            # Only arm an exit when the subject is actually moving in the
            # exit/door area. Standing still near the door is not absence.
            if (
                zone == "EXIT"
                and speed is not None
                and speed >= EXIT_SPEED_MIN
            ):
                state.exit_armed = True

            elif zone != "EXIT":
                state.exit_armed = False

            return self._snapshot(
                state,
                inferred=False,
                mode="LIVE",
                now=now,
            )

        # ----------------------------------------------------
        # No validated radar target exists in this update.
        # ----------------------------------------------------
        if (
            not state.present
            or state.last_detection_at is None
        ):
            state.present = False

            return self._snapshot(
                state,
                inferred=False,
                mode="ABSENT",
                now=now,
            )

        seconds_since_detection = max(
            0.0,
            (
                now
                - state.last_detection_at
            ).total_seconds(),
        )

        # Person was moving through the exit area and then disappeared.
        # After 10 seconds with no re-detection, classify as absent.
        if (
            state.exit_armed
            and seconds_since_detection
            >= EXIT_CONFIRM_SECONDS
        ):
            state.present = False
            state.exit_armed = False

            return self._snapshot(
                state,
                inferred=False,
                mode="ABSENT_EXIT",
                now=now,
            )

        bed_hold = (
            state.last_zone == "BED"
            and (
                state.last_speed is None
                or state.last_speed <= 0.10
            )
        )

        hold_seconds = (
            BED_HOLD_SECONDS
            if bed_hold
            else GENERAL_HOLD_SECONDS
        )

        if seconds_since_detection <= hold_seconds:
            state.present = True

            if state.exit_armed:
                mode = "EXIT_PENDING"
            elif bed_hold:
                mode = "HELD_BED"
            else:
                mode = "HELD_STATIC"

            return self._snapshot(
                state,
                inferred=True,
                mode=mode,
                now=now,
            )

        # Safety timeout for cases where no exit evidence was observed.
        state.present = False
        state.exit_armed = False

        return self._snapshot(
            state,
            inferred=False,
            mode="ABSENT_TIMEOUT",
            now=now,
        )

    @staticmethod
    def _snapshot(
        state: OccupancyTrack,
        *,
        inferred: bool,
        mode: str,
        now: datetime,
    ) -> dict:
        if state.last_detection_at is None:
            seconds_since_detection = None
        else:
            seconds_since_detection = max(
                0.0,
                (
                    now
                    - state.last_detection_at
                ).total_seconds(),
            )

        return {
            "present": state.present,
            "inferred": inferred,
            "mode": mode,
            "zone": state.last_zone,
            "seconds_since_detection": seconds_since_detection,
            "last_known_position": {
                "target_id": state.last_target_id,
                "x": state.last_x,
                "y": state.last_y,
                "z": state.last_z,
                "speed": state.last_speed,
            },
        }


occupancy_manager = OccupancyManager()
