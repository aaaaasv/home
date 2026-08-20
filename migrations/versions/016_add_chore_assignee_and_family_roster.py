"""tag a chore to a person and remember the household roster

Revision ID: 016
Revises: 015
Create Date: 2026-07-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chores", sa.Column("assignee_telegram_user_id", sa.BigInteger(), nullable=True))
    op.add_column("chores", sa.Column("assignee_display_name", sa.String(length=128), nullable=True))

    op.create_table(
        "family_members",
        sa.Column("telegram_user_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("telegram_user_id"),
    )


def downgrade() -> None:
    op.drop_table("family_members")
    op.drop_column("chores", "assignee_display_name")
    op.drop_column("chores", "assignee_telegram_user_id")
