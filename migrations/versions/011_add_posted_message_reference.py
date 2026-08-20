"""let a posted message name the one thing it is about

Revision ID: 011
Revises: 010
Create Date: 2026-07-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("posted_messages", schema=None) as batch_op:
        batch_op.add_column(sa.Column("reference", sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("posted_messages", schema=None) as batch_op:
        batch_op.drop_column("reference")
