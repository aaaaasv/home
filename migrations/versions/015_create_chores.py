"""chores: things to do, with an optional deadline that reminds

Revision ID: 015
Revises: 014
Create Date: 2026-07-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chores",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("added_by_telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("added_by_display_name", sa.String(length=128), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("completed_by_display_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chores_completed_at_due_on", "chores", ["completed_at", "due_on"], unique=False)

    op.create_table(
        "chores_list_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("chores_list_messages")
    op.drop_index("ix_chores_completed_at_due_on", table_name="chores")
    op.drop_table("chores")
