"""give every active plant a photo schedule

Revision ID: 010
Revises: 009
Create Date: 2026-07-23

"""
from datetime import date, datetime, timedelta, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PHOTO_TASK_TYPE = "photo"
PHOTO_INTERVAL_DAYS = 30

PHOTO_INSTRUCTIONS = (
    "Знімай при денному світлі з того самого боку, що й минулого разу — тоді видно, що змінилося. "
    "Один кадр загальний, один крупно на листя згори і знизу: шкідники та плями зʼявляються там першими."
)


def upgrade() -> None:
    connection = op.get_bind()
    plants = connection.execute(
        sa.text(
            "SELECT p.id, MAX(ph.taken_at) AS last_taken_at "
            "FROM plants p LEFT JOIN plant_photos ph ON ph.plant_id = p.id "
            "WHERE p.is_archived = 0 GROUP BY p.id ORDER BY p.id"
        )
    ).all()
    if not plants:
        return

    today = date.today()
    for position, (plant_id, last_taken_at) in enumerate(plants):
        # spread the first round evenly over one interval, so the plants never all come due on the same day
        earliest = max(_next_after(last_taken_at), today)
        next_due_on = earliest + timedelta(days=position * PHOTO_INTERVAL_DAYS // len(plants))
        connection.execute(
            sa.text(
                "INSERT INTO care_schedules "
                "(plant_id, task_type, interval_days, next_due_on, instructions, created_at, updated_at) "
                "VALUES (:plant_id, :task_type, :interval_days, :next_due_on, :instructions, :now, :now)"
            ),
            {
                "plant_id": plant_id,
                "task_type": PHOTO_TASK_TYPE,
                "interval_days": PHOTO_INTERVAL_DAYS,
                "next_due_on": next_due_on,
                "instructions": PHOTO_INSTRUCTIONS,
                # sqlite keeps no offset, so store the same naive utc shape the orm writes
                "now": datetime.now(timezone.utc).replace(tzinfo=None),
            },
        )


def _next_after(last_taken_at: str | None) -> date:
    if last_taken_at is None:
        return date.min
    return date.fromisoformat(last_taken_at[:10]) + timedelta(days=PHOTO_INTERVAL_DAYS)


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM care_schedules WHERE task_type = :task_type"), {"task_type": PHOTO_TASK_TYPE}
    )
