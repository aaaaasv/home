"""Keep what every sensor measured — raw for a few days, folded per day for good

Revision ID: 031
Revises: 030
"""

import sqlalchemy as sa
from alembic import op

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sensor_readings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sensor", sa.String(length=48), nullable=False),
        sa.Column("room", sa.String(length=32), nullable=True),
        sa.Column("temperature_celsius", sa.Float(), nullable=True),
        sa.Column("relative_humidity_percent", sa.Float(), nullable=True),
        sa.Column("soil_moisture_percent", sa.Float(), nullable=True),
        sa.Column("battery_percent", sa.Float(), nullable=True),
        sa.Column("measured_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sensor_readings_sensor_measured_at", "sensor_readings", ["sensor", "measured_at"])

    op.create_table(
        "sensor_days",
        sa.Column("sensor", sa.String(length=48), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("room", sa.String(length=32), nullable=True),
        sa.Column("reading_count", sa.Integer(), nullable=False),
        sa.Column("minimum_temperature_celsius", sa.Float(), nullable=True),
        sa.Column("maximum_temperature_celsius", sa.Float(), nullable=True),
        sa.Column("average_temperature_celsius", sa.Float(), nullable=True),
        sa.Column("minimum_humidity_percent", sa.Float(), nullable=True),
        sa.Column("maximum_humidity_percent", sa.Float(), nullable=True),
        sa.Column("average_humidity_percent", sa.Float(), nullable=True),
        sa.Column("minimum_soil_moisture_percent", sa.Float(), nullable=True),
        sa.Column("maximum_soil_moisture_percent", sa.Float(), nullable=True),
        sa.Column("average_soil_moisture_percent", sa.Float(), nullable=True),
        sa.Column("minimum_battery_percent", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("sensor", "day"),
    )
    op.create_index("ix_sensor_days_day", "sensor_days", ["day"])


def downgrade() -> None:
    op.drop_index("ix_sensor_days_day", table_name="sensor_days")
    op.drop_table("sensor_days")
    op.drop_index("ix_sensor_readings_sensor_measured_at", table_name="sensor_readings")
    op.drop_table("sensor_readings")
