"""Give a plant the room whose sensor speaks for its air

Revision ID: 032
Revises: 031
"""

import sqlalchemy as sa
from alembic import op

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # deliberately left empty for every existing plant: until somebody says which room a plant is in, the honest
    # answer is that the bot does not know, and a plant with no room gets no comfort verdict rather than a wrong one
    op.add_column("plants", sa.Column("room", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("plants", "room")
