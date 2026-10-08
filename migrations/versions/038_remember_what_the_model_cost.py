"""Remember what every paid model call cost

Revision ID: 038
Revises: 037
"""
import sqlalchemy as sa
from alembic import op

from src.infrastructure.db.types import UtcDateTime

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_usage",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_micro_usd", sa.Integer(), nullable=False),
        sa.Column("at", UtcDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_model_usage_at", "model_usage", ["at"])


def downgrade() -> None:
    op.drop_index("ix_model_usage_at", table_name="model_usage")
    op.drop_table("model_usage")
