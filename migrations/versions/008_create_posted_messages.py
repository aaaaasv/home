"""create posted messages table

Revision ID: 008
Revises: 007
Create Date: 2026-07-21

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from src.infrastructure.db.types import UtcDateTime

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "posted_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("posted_messages", schema=None) as batch_op:
        batch_op.create_index("ix_posted_messages_kind", ["kind"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("posted_messages", schema=None) as batch_op:
        batch_op.drop_index("ix_posted_messages_kind")
    op.drop_table("posted_messages")
