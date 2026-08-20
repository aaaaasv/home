"""create forum topics table

Revision ID: 002
Revises: 001
Create Date: 2026-07-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from src.infrastructure.db.types import UtcDateTime

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "forum_topics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("module_name", sa.String(length=32), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_thread_id", sa.Integer(), nullable=False),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.Column("updated_at", UtcDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("module_name"),
    )


def downgrade() -> None:
    op.drop_table("forum_topics")
