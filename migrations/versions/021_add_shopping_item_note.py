"""add note to shopping items

Revision ID: 021
Revises: 020
Create Date: 2026-08-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("shopping_items", sa.Column("note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("shopping_items", "note")
