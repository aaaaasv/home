"""create shopping tables

Revision ID: 003
Revises: 002
Create Date: 2026-07-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from src.infrastructure.db.types import UtcDateTime

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shopping_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("horizon", sa.String(length=8), nullable=False),
        sa.Column("added_by_telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("added_by_display_name", sa.String(length=128), nullable=False),
        sa.Column("bought_at", UtcDateTime(), nullable=True),
        sa.Column("bought_by_display_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shopping_items_bought_at_horizon", "shopping_items", ["bought_at", "horizon"])

    op.create_table(
        "shopping_list_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("shopping_list_messages")
    op.drop_index("ix_shopping_items_bought_at_horizon", table_name="shopping_items")
    op.drop_table("shopping_items")
