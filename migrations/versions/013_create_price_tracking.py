"""track hotline prices for shopping items

Revision ID: 013
Revises: 012
Create Date: 2026-07-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("shopping_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("hotline_url", sa.String(length=512), nullable=True))

    op.create_table(
        "price_checks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("shopping_item_id", sa.Integer(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["shopping_item_id"], ["shopping_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_price_checks_item_id_checked_at", "price_checks", ["shopping_item_id", "checked_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_price_checks_item_id_checked_at", table_name="price_checks")
    op.drop_table("price_checks")
    with op.batch_alter_table("shopping_items", schema=None) as batch_op:
        batch_op.drop_column("hotline_url")
