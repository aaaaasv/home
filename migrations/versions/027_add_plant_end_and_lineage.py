"""Record the day a plant ended and the plant it was taken from

Revision ID: 027
Revises: 026
"""

import sqlalchemy as sa
from alembic import op

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # both are nullable and nothing is backfilled: is_archived never carried a date, and updated_at is touched
    # by any edit, so inventing an end date from it would put a wrong one on a sheet that reads as a record
    op.add_column("plants", sa.Column("archived_on", sa.Date(), nullable=True))
    op.add_column("plants", sa.Column("propagated_from_plant_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("plants", "propagated_from_plant_id")
    op.drop_column("plants", "archived_on")
