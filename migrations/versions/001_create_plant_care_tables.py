"""create plant care tables

Revision ID: 001
Revises:
Create Date: 2026-07-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from src.infrastructure.db.types import UtcDateTime

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("species", sa.String(length=128), nullable=True),
        sa.Column("location", sa.String(length=128), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("added_by_telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.Column("updated_at", UtcDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("plants", schema=None) as batch_op:
        batch_op.create_index("ix_plants_is_archived_name", ["is_archived", "name"], unique=False)
        batch_op.create_index("uq_plants_active_name", ["name"], unique=True, sqlite_where=sa.text("is_archived = 0"))

    op.create_table(
        "care_schedules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plant_id", sa.Integer(), nullable=False),
        sa.Column("task_type", sa.String(length=20), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("next_due_on", sa.Date(), nullable=False),
        sa.Column("last_performed_at", UtcDateTime(), nullable=True),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.Column("updated_at", UtcDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plant_id", "task_type", name="uq_care_schedules_plant_task_type"),
    )
    with op.batch_alter_table("care_schedules", schema=None) as batch_op:
        batch_op.create_index("ix_care_schedules_next_due_on", ["next_due_on"], unique=False)
        batch_op.create_index("ix_care_schedules_plant_id", ["plant_id"], unique=False)

    op.create_table(
        "care_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plant_id", sa.Integer(), nullable=False),
        sa.Column("task_type", sa.String(length=20), nullable=False),
        sa.Column("performed_at", UtcDateTime(), nullable=False),
        sa.Column("performed_by_telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("performed_by_display_name", sa.String(length=128), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("care_events", schema=None) as batch_op:
        batch_op.create_index(
            "ix_care_events_plant_id_task_type_performed_at",
            ["plant_id", "task_type", "performed_at"],
            unique=False,
        )

    op.create_table(
        "plant_photos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plant_id", sa.Integer(), nullable=False),
        sa.Column("telegram_file_id", sa.String(length=255), nullable=False),
        sa.Column("telegram_file_unique_id", sa.String(length=64), nullable=False),
        sa.Column("local_path", sa.String(length=512), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("added_by_telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("taken_at", UtcDateTime(), nullable=False),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("plant_photos", schema=None) as batch_op:
        batch_op.create_index("ix_plant_photos_plant_id_taken_at", ["plant_id", "taken_at"], unique=False)


def downgrade() -> None:
    op.drop_table("plant_photos")
    op.drop_table("care_events")
    op.drop_table("care_schedules")
    op.drop_table("plants")
