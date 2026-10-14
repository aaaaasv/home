"""Remember who is feeding the socket the hat measures

Revision ID: 041
Revises: 040
"""
import sqlalchemy as sa
from alembic import op

from src.infrastructure.db.types import UtcDateTime

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supply_declaration",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("supply", sa.String(length=16), nullable=False),
        sa.Column("declared_at", UtcDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("supply_declaration")
