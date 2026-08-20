"""add manual override to conservation state

Revision ID: 020
Revises: 019
Create Date: 2026-08-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("conservation_state", schema=None) as batch_op:
        batch_op.add_column(sa.Column("manual_override", sa.Boolean(), server_default="0", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("conservation_state", schema=None) as batch_op:
        batch_op.drop_column("manual_override")
