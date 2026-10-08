"""Remember when the grid went, and what the air outside was doing

Revision ID: 039
Revises: 038
"""
import sqlalchemy as sa
from alembic import op

from src.infrastructure.db.types import UtcDateTime

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outdoor_weather_days",
        sa.Column("day", sa.Date(), autoincrement=False, nullable=False),
        sa.Column("reading_count", sa.Integer(), nullable=False),
        sa.Column("minimum_temperature_celsius", sa.Float(), nullable=True),
        sa.Column("maximum_temperature_celsius", sa.Float(), nullable=True),
        sa.Column("average_temperature_celsius", sa.Float(), nullable=True),
        sa.Column("minimum_humidity_percent", sa.Float(), nullable=True),
        sa.Column("maximum_humidity_percent", sa.Float(), nullable=True),
        sa.Column("average_humidity_percent", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("day"),
    )
    op.create_table(
        "grid_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("at", UtcDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_grid_events_at", "grid_events", ["at"])


def downgrade() -> None:
    op.drop_index("ix_grid_events_at", table_name="grid_events")
    op.drop_table("grid_events")
    op.drop_table("outdoor_weather_days")
