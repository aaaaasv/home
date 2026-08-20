"""add per-plant ideal climate ranges and their alert state

Revision ID: 006
Revises: 005
Create Date: 2026-07-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from src.infrastructure.db.types import UtcDateTime

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("plants", sa.Column("ideal_temperature_min_celsius", sa.Float(), nullable=True))
    op.add_column("plants", sa.Column("ideal_temperature_max_celsius", sa.Float(), nullable=True))
    op.add_column("plants", sa.Column("ideal_humidity_min_percent", sa.Float(), nullable=True))
    op.add_column("plants", sa.Column("ideal_humidity_max_percent", sa.Float(), nullable=True))

    op.create_table(
        "plant_climate_alerts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plant_id", sa.Integer(), nullable=False),
        sa.Column("dimension", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("notified_at", UtcDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_plant_climate_alerts_plant_dimension_id",
        "plant_climate_alerts",
        ["plant_id", "dimension", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_plant_climate_alerts_plant_dimension_id", table_name="plant_climate_alerts")
    op.drop_table("plant_climate_alerts")
    with op.batch_alter_table("plants") as batch:
        batch.drop_column("ideal_humidity_max_percent")
        batch.drop_column("ideal_humidity_min_percent")
        batch.drop_column("ideal_temperature_max_celsius")
        batch.drop_column("ideal_temperature_min_celsius")
