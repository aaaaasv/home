"""Tell a general frame from a close-up, so only comparable photos are compared

Revision ID: 025
Revises: 024
"""

import sqlalchemy as sa
from alembic import op

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # every photo so far was a lone shot taken on its own day, so all of them are the frame growth is measured
    # against — backfilling them as overview leaves every existing comparison exactly as it was
    op.add_column("plant_photos", sa.Column("frame", sa.String(16), nullable=False, server_default="overview"))


def downgrade() -> None:
    op.drop_column("plant_photos", "frame")
