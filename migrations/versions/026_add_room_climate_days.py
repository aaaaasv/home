"""Fold each day's climate into one row, so a photo six weeks old has air to be judged against

Revision ID: 026
Revises: 025
"""

import sqlalchemy as sa
from alembic import op

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # nothing is backfilled: the raw table only ever holds two days, so there is no history to fold. the record
    # starts today and grows one row a day
    op.create_table(
        "room_climate_days",
        sa.Column("day", sa.Date(), primary_key=True, autoincrement=False),
        sa.Column("minimum_temperature_celsius", sa.Float(), nullable=False),
        sa.Column("maximum_temperature_celsius", sa.Float(), nullable=False),
        sa.Column("average_temperature_celsius", sa.Float(), nullable=False),
        sa.Column("minimum_humidity_percent", sa.Float(), nullable=False),
        sa.Column("maximum_humidity_percent", sa.Float(), nullable=False),
        sa.Column("average_humidity_percent", sa.Float(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("room_climate_days")
