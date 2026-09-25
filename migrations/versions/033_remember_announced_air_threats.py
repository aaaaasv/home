"""Remember which air threats the household was already told about

Revision ID: 033
Revises: 032
"""

import sqlalchemy as sa
from alembic import op

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "air_threat_notices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tracker_id", sa.String(length=48), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("rendered_text", sa.Text(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tracker_id"),
    )
    op.create_index("ix_air_threat_notices_closed_at", "air_threat_notices", ["closed_at"])


def downgrade() -> None:
    op.drop_index("ix_air_threat_notices_closed_at", table_name="air_threat_notices")
    op.drop_table("air_threat_notices")
