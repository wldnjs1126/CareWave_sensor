from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


# ============================================================
# CareWave test-room geometry
# ============================================================
#
# Radar coordinate system:
#   X: left (-) <---- 0 ----> right (+)
#   Y: radar (0) -----------> upper/opposite wall (3.8 m)
#
# Room:
#   width  = 3.6 m
#   depth  = 3.8 m
#
ROOM_X_MIN = -1.8
ROOM_X_MAX = 1.8
ROOM_Y_MIN = 0.0
ROOM_Y_MAX = 3.8


# ============================================================
# Bed zone
# ============================================================
#
# Horizontal bed, attached to the left wall.
#
BED_X_MIN = -1.8
BED_X_MAX = 0.0
BED_Y_MIN = 1.6
BED_Y_MAX = 2.6


# ============================================================
# Test-room door / exit zone
# ============================================================
#
# The test exit is the passage between:
#   - the air purifier near the upper wall
#   - the movable whiteboard / partition on the right
#
EXIT_X_MIN = 0.95
EXIT_X_MAX = 1.65
EXIT_Y_MIN = 2.90
EXIT_Y_MAX = 3.70

# A broader approach area helps preserve an exit transition when the
# 1-second aggregation jumps from ROOM directly to OUTSIDE.
EXIT_APPROACH_X_MIN = 0.70
EXIT_APPROACH_X_MAX = 1.80
EXIT_APPROACH_Y_MIN = 2.55

# Movement threshold already used by CareWave.
EXIT_SPEED_MIN = 0.10

# After a confirmed exit transition, 10 seconds without returning inside
# the room is enough to classify absence.
EXIT_CONFIRM_SECONDS = 10


# ============================================================
# Missing-target holds
# ============================================================
#
# A missing instant target is NOT automatically absence.
#
# If the person was moving when the target vanished, only hold briefly.
# A moving person should normally be reacquired quickly unless they left.
MOVING_HOLD_SECONDS = 20

# A confirmed low-motion person may disappear from instant radar tracking.
# Keep occupancy long enough for the 30-minute INACTIVITY rule.
STATIC_SPEED_MAX = 0.10
STATIC_HOLD_SECONDS = 35 * 60

# Bed low-motion state must remain long enough for sleep monitoring.
BED_HOLD_SECONDS = 12 * 60 * 60


@dataclass
class OccupancyTrack:
    present: bool = False

    # Last TRUSTED position inside ROOM / BED / EXIT.
    # OUTSIDE detections do not refresh this timestamp.
    last_detection_at: datetime | None = None

    last_target_id: int | None = None
    last_x: float | None = None
    last_y: float | None = None
    last_z: float | None = None
    last_speed: float | None = None
    last_zone: str | None = None

    # Exit state.
    exit_armed: bool = False
    exit_started_at: datetime | None = None
    outside_since: datetime | None = None


class OccupancyManager:
    """
    Separates three concepts:

    1) Instant radar target:
       A validated target exists in the current sensor update.

    2) Trusted in-room position:
       A target is physically inside ROOM / BED / EXIT.

    3) Occupancy:
       CareWave's stateful decision that a person is still in the room.

    Important:
    - OUTSIDE targets do not automatically create/refresh room occupancy.
    - A confirmed EXIT -> OUTSIDE transition is preserved until absence.
    - Stationary target loss is handled by timed occupancy inference.
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
            EXIT_X_MIN <= x <= EXIT_X_MAX
            and EXIT_Y_MIN <= y <= EXIT_Y_MAX
        ):
            return "EXIT"

        if (
            ROOM_X_MIN <= x <= ROOM_X_MAX
            and ROOM_Y_MIN <= y <= ROOM_Y_MAX
        ):
            return "ROOM"

        return "OUTSIDE"

    @staticmethod
    def is_exit_approach(
        x: float | None,
        y: float | None,
    ) -> bool:
        if x is None or y is None:
            return False

        return (
            EXIT_APPROACH_X_MIN <= x <= EXIT_APPROACH_X_MAX
            and y >= EXIT_APPROACH_Y_MIN
        )

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

    @staticmethod
    def _clear_exit(
        state: OccupancyTrack,
    ) -> None:
        state.exit_armed = False
        state.exit_started_at = None
        state.outside_since = None

    @staticmethod
    def _arm_exit(
        state: OccupancyTrack,
        now: datetime,
    ) -> None:
        if not state.exit_armed:
            state.exit_armed = True
            state.exit_started_at = now

        state.outside_since = None

    @staticmethod
    def _set_trusted_target(
        state: OccupancyTrack,
        *,
        now: datetime,
        target_id: int | None,
        x: float | None,
        y: float | None,
        z: float | None,
        speed: float | None,
        zone: str,
    ) -> None:
        state.last_detection_at = now

        state.last_target_id = target_id
        state.last_x = x
        state.last_y = y
        state.last_z = z
        state.last_speed = speed
        state.last_zone = zone

    def _confirm_exit_absence(
        self,
        state: OccupancyTrack,
        now: datetime,
    ) -> dict:
        state.present = False

        # Keep EXIT as the last trusted zone. Do not replace the last trusted
        # position with a possible OUTSIDE ghost target.
        state.last_zone = "EXIT"

        self._clear_exit(state)

        return self._snapshot(
            state,
            inferred=False,
            mode="ABSENT_EXIT",
            now=now,
        )

    def _handle_no_trusted_target(
        self,
        state: OccupancyTrack,
        now: datetime,
    ) -> dict:
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

        # ----------------------------------------------------
        # Exit was already armed.
        # Missing/OUTSIDE observations must NOT cancel it.
        # ----------------------------------------------------
        if state.exit_armed:
            if state.outside_since is None:
                state.outside_since = now

            outside_seconds = max(
                0.0,
                (
                    now
                    - state.outside_since
                ).total_seconds(),
            )

            if outside_seconds >= EXIT_CONFIRM_SECONDS:
                return self._confirm_exit_absence(
                    state,
                    now,
                )

            state.present = True

            return self._snapshot(
                state,
                inferred=True,
                mode="EXIT_PENDING",
                now=now,
            )

        seconds_since_detection = max(
            0.0,
            (
                now
                - state.last_detection_at
            ).total_seconds(),
        )

        low_motion = (
            state.last_speed is None
            or state.last_speed <= STATIC_SPEED_MAX
        )

        if (
            state.last_zone == "BED"
            and low_motion
        ):
            hold_seconds = BED_HOLD_SECONDS
            mode = "HELD_BED"

        elif low_motion:
            hold_seconds = STATIC_HOLD_SECONDS
            mode = "HELD_STATIC"

        else:
            hold_seconds = MOVING_HOLD_SECONDS
            mode = "HELD_MOVING"

        if seconds_since_detection <= hold_seconds:
            state.present = True

            return self._snapshot(
                state,
                inferred=True,
                mode=mode,
                now=now,
            )

        state.present = False
        self._clear_exit(state)

        return self._snapshot(
            state,
            inferred=False,
            mode="ABSENT_TIMEOUT",
            now=now,
        )

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
        # No instant radar target.
        # ----------------------------------------------------
        if not detected:
            return self._handle_no_trusted_target(
                state,
                now,
            )

        zone = self.classify_zone(
            x,
            y,
        )

        # ----------------------------------------------------
        # ROOM / BED:
        # definitely back inside -> cancel exit state.
        # ----------------------------------------------------
        if zone in {"ROOM", "BED"}:
            state.present = True

            self._set_trusted_target(
                state,
                now=now,
                target_id=target_id,
                x=x,
                y=y,
                z=z,
                speed=speed,
                zone=zone,
            )

            self._clear_exit(state)

            return self._snapshot(
                state,
                inferred=False,
                mode="LIVE",
                now=now,
            )

        # ----------------------------------------------------
        # EXIT:
        # trusted location, but do not call absence yet.
        # ----------------------------------------------------
        if zone == "EXIT":
            state.present = True

            self._set_trusted_target(
                state,
                now=now,
                target_id=target_id,
                x=x,
                y=y,
                z=z,
                speed=speed,
                zone="EXIT",
            )

            if (
                state.exit_armed
                or (
                    speed is not None
                    and speed >= EXIT_SPEED_MIN
                )
            ):
                self._arm_exit(
                    state,
                    now,
                )

                return self._snapshot(
                    state,
                    inferred=False,
                    mode="EXIT_PENDING",
                    now=now,
                )

            return self._snapshot(
                state,
                inferred=False,
                mode="LIVE",
                now=now,
            )

        # ----------------------------------------------------
        # OUTSIDE:
        #
        # Never let an OUTSIDE target create or refresh room presence.
        # This prevents objects near/behind the upper wall (for example the
        # air purifier / stale TI track) from becoming a new resident target.
        #
        # If a real exit was already armed, OUTSIDE is evidence supporting
        # the exit transition and starts/continues the 10-second timer.
        # ----------------------------------------------------
        if zone == "OUTSIDE":
            if state.exit_armed:
                if state.outside_since is None:
                    state.outside_since = now

                outside_seconds = max(
                    0.0,
                    (
                        now
                        - state.outside_since
                    ).total_seconds(),
                )

                if outside_seconds >= EXIT_CONFIRM_SECONDS:
                    return self._confirm_exit_absence(
                        state,
                        now,
                    )

                state.present = True

                return self._snapshot(
                    state,
                    inferred=True,
                    mode="EXIT_PENDING",
                    now=now,
                )

            # The 1-second average can jump over the narrow EXIT rectangle.
            # If the last trusted point was already close to the exit and the
            # new target is OUTSIDE on the same side, arm an exit transition.
            if (
                state.present
                and self.is_exit_approach(
                    state.last_x,
                    state.last_y,
                )
                and (
                    state.last_speed is None
                    or state.last_speed >= EXIT_SPEED_MIN
                )
            ):
                self._arm_exit(
                    state,
                    now,
                )
                state.outside_since = now

                return self._snapshot(
                    state,
                    inferred=True,
                    mode="EXIT_PENDING",
                    now=now,
                )

            # Otherwise ignore the OUTSIDE target completely and process it
            # exactly like a missing/untrusted target.
            return self._handle_no_trusted_target(
                state,
                now,
            )

        # Missing coordinates / unknown classification.
        return self._handle_no_trusted_target(
            state,
            now,
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
