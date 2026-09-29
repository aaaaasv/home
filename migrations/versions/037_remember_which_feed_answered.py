"""Remember which feed answered each alert reading

Revision ID: 037
Revises: 036
"""
import sqlalchemy as sa
from alembic import op

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("air_alert_events", sa.Column("source", sa.String(length=12), nullable=True))


def downgrade() -> None:
    op.drop_column("air_alert_events", "source")
