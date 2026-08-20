"""create room climate tables

Revision ID: 004
Revises: 003
Create Date: 2026-07-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from src.infrastructure.db.types import UtcDateTime

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "room_climate_readings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("temperature_celsius", sa.Float(), nullable=False),
        sa.Column("relative_humidity_percent", sa.Float(), nullable=False),
        sa.Column("measured_at", UtcDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_room_climate_readings_measured_at", "room_climate_readings", ["measured_at"])

    op.create_table(
        "room_climate_alerts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("is_air_dry", sa.Boolean(), nullable=False),
        sa.Column("relative_humidity_percent", sa.Float(), nullable=False),
        sa.Column("changed_at", UtcDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("room_climate_alerts")
    op.drop_index("ix_room_climate_readings_measured_at", table_name="room_climate_readings")
    op.drop_table("room_climate_readings")
