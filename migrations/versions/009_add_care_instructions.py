"""add per-task care instructions

Revision ID: 009
Revises: 008
Create Date: 2026-07-21

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("care_schedules", schema=None) as batch_op:
        batch_op.add_column(sa.Column("instructions", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("care_schedules", schema=None) as batch_op:
        batch_op.drop_column("instructions")
