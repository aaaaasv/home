"""attach a photo to a shopping item

Revision ID: 017
Revises: 016
Create Date: 2026-07-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("shopping_items", sa.Column("photo_telegram_file_id", sa.String(length=256), nullable=True))


def downgrade() -> None:
    op.drop_column("shopping_items", "photo_telegram_file_id")
