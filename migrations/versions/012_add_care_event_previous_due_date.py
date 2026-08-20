"""remember the due date a care record replaced, so it can be undone exactly

Revision ID: 012
Revises: 011
Create Date: 2026-07-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("care_events", schema=None) as batch_op:
        batch_op.add_column(sa.Column("previous_next_due_on", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("care_events", schema=None) as batch_op:
        batch_op.drop_column("previous_next_due_on")
