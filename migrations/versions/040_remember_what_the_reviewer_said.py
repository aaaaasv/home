"""Remember what the reviewer said about each photo

Revision ID: 040
Revises: 039
"""
import sqlalchemy as sa
from alembic import op

from src.infrastructure.db.types import UtcDateTime

revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plant_photo_reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plant_id", sa.Integer(), nullable=False),
        sa.Column("photo_id", sa.Integer(), nullable=False),
        sa.Column("compared_to_photo_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("change", sa.Text(), nullable=True),
        sa.Column("action", sa.Text(), nullable=True),
        sa.Column("at", UtcDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["photo_id"], ["plant_photos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["compared_to_photo_id"], ["plant_photos.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plant_photo_reviews_plant_id_at", "plant_photo_reviews", ["plant_id", "at"])


def downgrade() -> None:
    op.drop_index("ix_plant_photo_reviews_plant_id_at", table_name="plant_photo_reviews")
    op.drop_table("plant_photo_reviews")
