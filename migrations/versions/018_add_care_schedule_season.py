"""add growing-season window to care schedules

Revision ID: 018
Revises: 017
Create Date: 2026-08-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("care_schedules", schema=None) as batch_op:
        batch_op.add_column(sa.Column("season_start_month", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("season_end_month", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("care_schedules", schema=None) as batch_op:
        batch_op.drop_column("season_end_month")
        batch_op.drop_column("season_start_month")
