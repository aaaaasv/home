"""Remember every alert level, not only the current one

Revision ID: 036
Revises: 035
"""
import sqlalchemy as sa
from alembic import op

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "air_alert_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("level", sa.String(length=8), nullable=False),
        sa.Column("reason", sa.String(length=160), nullable=True),
        sa.Column("outcome", sa.String(length=24), nullable=True),
        sa.Column("at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_air_alert_events_at", "air_alert_events", ["at"])


def downgrade() -> None:
    op.drop_index("ix_air_alert_events_at", table_name="air_alert_events")
    op.drop_table("air_alert_events")
