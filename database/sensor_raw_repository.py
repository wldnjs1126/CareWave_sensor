from sqlalchemy import text

from database.connection import engine


INSERT_SENSOR_RAW = text(
    """
    INSERT INTO sensor_raw (
        sensor_id,
        subject_id,
        window_start,
        window_end,
        sample_count,
        presence,
        avg_x,
        avg_y,
        avg_z,
        min_z,
        avg_velocity_x,
        avg_velocity_y,
        avg_velocity_z,
        min_velocity_z,
        avg_speed,
        max_speed,
        avg_acceleration_z,
        min_acceleration_z,
        avg_height,
        min_height,
        avg_movement_level,
        zone,
        created_at
    ) VALUES (
        :sensor_id,
        :subject_id,
        :window_start,
        :window_end,
        :sample_count,
        :presence,
        :avg_x,
        :avg_y,
        :avg_z,
        :min_z,
        :avg_velocity_x,
        :avg_velocity_y,
        :avg_velocity_z,
        :min_velocity_z,
        :avg_speed,
        :max_speed,
        :avg_acceleration_z,
        :min_acceleration_z,
        :avg_height,
        :min_height,
        :avg_movement_level,
        :zone,
        :created_at
    )
    """
)


def save_sensor_raw(row: dict) -> None:
    with engine.begin() as conn:
        conn.execute(INSERT_SENSOR_RAW, row)
