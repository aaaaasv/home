"""Remember each week's printed paper

Revision ID: 029
Revises: 028
"""

import sqlalchemy as sa
from alembic import op

from src.infrastructure.db.types import UtcDateTime

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "newspaper_issues",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("number", sa.Integer(), nullable=False, unique=True),
        sa.Column("week_starts_on", sa.Date(), nullable=False, unique=True),
        sa.Column("crossword", sa.JSON(), nullable=False),
        sa.Column("printed_at", UtcDateTime(), nullable=True),
        sa.Column("created_at", UtcDateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("newspaper_issues")
