"""track continuous air conditioner runs so a forgotten unit can be noticed

Revision ID: 007
Revises: 006
Create Date: 2026-07-20

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from src.infrastructure.db.types import UtcDateTime

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "air_conditioner_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("started_at", UtcDateTime(), nullable=False),
        sa.Column("ended_at", UtcDateTime(), nullable=True),
        sa.Column("notified_at", UtcDateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("air_conditioner_runs")
