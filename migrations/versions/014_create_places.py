"""places to visit, with a visited history

Revision ID: 014
Revises: 013
Create Date: 2026-07-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "places",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("link", sa.String(length=512), nullable=True),
        sa.Column("address", sa.String(length=256), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("setting", sa.String(length=8), nullable=True),
        sa.Column("added_by_telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("added_by_display_name", sa.String(length=128), nullable=False),
        sa.Column("visited_at", sa.DateTime(), nullable=True),
        sa.Column("visited_by_display_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_places_visited_at", "places", ["visited_at"], unique=False)

    op.create_table(
        "places_list_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("places_list_messages")
    op.drop_index("ix_places_visited_at", table_name="places")
    op.drop_table("places")
