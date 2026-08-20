"""Add a preferred name for family members and provenance fields for plants

Revision ID: 023
Revises: 022
"""

import sqlalchemy as sa
from alembic import op

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # telegram keeps supplying display_name and the roster middleware keeps overwriting it. this is the
    # name a person chose for themselves, so it always wins when set
    op.add_column("family_members", sa.Column("preferred_name", sa.String(128), nullable=True))

    # what a herbarium sheet records about a specimen beyond its schedule
    op.add_column("plants", sa.Column("provenance", sa.Text(), nullable=True))
    op.add_column("plants", sa.Column("native_range", sa.String(160), nullable=True))
    op.add_column("plants", sa.Column("substrate", sa.String(160), nullable=True))
    op.add_column("plants", sa.Column("toxicity", sa.String(160), nullable=True))


def downgrade() -> None:
    for column in ("toxicity", "substrate", "native_range", "provenance"):
        op.drop_column("plants", column)
    op.drop_column("family_members", "preferred_name")
