"""Remember who joined the Wi-Fi, when, and what the welcome light made of it

Revision ID: 035
Revises: 034
"""

import sqlalchemy as sa
from alembic import op

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "presence_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("mac", sa.String(length=24), nullable=False),
        sa.Column("event", sa.String(length=8), nullable=False),
        sa.Column("rssi", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(length=24), nullable=True),
        sa.Column("at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_presence_events_mac_at", "presence_events", ["mac", "at"])


def downgrade() -> None:
    op.drop_index("ix_presence_events_mac_at", table_name="presence_events")
    op.drop_table("presence_events")
