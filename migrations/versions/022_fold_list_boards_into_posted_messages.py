"""Fold the three list-board tables into posted_messages

Revision ID: 022
Revises: 021
"""

import sqlalchemy as sa
from alembic import op

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None

# shopping, places and chores each owned a one-row table holding the id of the message their list lives in —
# three tables, three repositories and three migrations for what posted_messages already does with a `kind`
FOLDED = (
    ("shopping_list_messages", "shopping_list"),
    ("places_list_messages", "places_list"),
    ("chores_list_messages", "chores_list"),
)


def upgrade() -> None:
    for table, kind in FOLDED:
        op.execute(
            sa.text(
                f"INSERT INTO posted_messages (kind, reference, chat_id, message_id, created_at) "
                f"SELECT '{kind}', NULL, chat_id, message_id, CURRENT_TIMESTAMP FROM {table}"  # noqa: S608
            )
        )
        op.drop_table(table)


def downgrade() -> None:
    for table, kind in FOLDED:
        op.create_table(
            table,
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("chat_id", sa.BigInteger(), nullable=False),
            sa.Column("message_id", sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.execute(
            sa.text(
                f"INSERT INTO {table} (chat_id, message_id) "  # noqa: S608
                f"SELECT chat_id, message_id FROM posted_messages WHERE kind = '{kind}'"
            )
        )
        op.execute(sa.text(f"DELETE FROM posted_messages WHERE kind = '{kind}'"))
