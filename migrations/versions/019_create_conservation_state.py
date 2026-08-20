"""create conservation state for the ecoflow station

Revision ID: 019
Revises: 018
Create Date: 2026-08-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conservation_state",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("stored_percent", sa.Float(), nullable=False),
        sa.Column("stored_at", sa.DateTime(), nullable=False),
        sa.Column("mode", sa.String(length=8), server_default="off", nullable=False),
        sa.Column("last_cycle_at", sa.DateTime(), nullable=True),
        sa.Column("is_conserved", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("saw_low_since_cycle", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("last_advised_level", sa.String(length=8), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("conservation_state")
