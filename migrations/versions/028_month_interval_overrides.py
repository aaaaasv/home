"""Replace the growing-season window with per-month interval overrides

Revision ID: 028
Revises: 027
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None

MONTHS_IN_YEAR = 12
ALL_MONTHS = range(1, MONTHS_IN_YEAR + 1)


def previous_month(month: int) -> int:
    return MONTHS_IN_YEAR if month == 1 else month - 1


def next_month(month: int) -> int:
    return 1 if month == MONTHS_IN_YEAR else month + 1


def list_months_outside(season_start_month: int, season_end_month: int) -> list[int]:
    if season_start_month <= season_end_month:
        inside = set(range(season_start_month, season_end_month + 1))
    else:
        inside = set(range(season_start_month, MONTHS_IN_YEAR + 1)) | set(range(1, season_end_month + 1))
    return [month for month in ALL_MONTHS if month not in inside]


def derive_window(active_months: set[int]) -> tuple[int, int] | None:
    """The window a set of active months collapses back into, or None when no single window can express it."""
    if len(active_months) in (0, MONTHS_IN_YEAR):
        return None
    starts = [month for month in sorted(active_months) if previous_month(month) not in active_months]
    ends = [month for month in sorted(active_months) if next_month(month) not in active_months]
    if len(starts) != 1 or len(ends) != 1:
        return None
    return starts[0], ends[0]


def upgrade() -> None:
    op.add_column("care_schedules", sa.Column("month_interval_overrides", sa.JSON(), nullable=True))

    # a window said "do this task only in these months", so every month outside it becomes an explicit skip.
    # that is the same behaviour in the new shape, so no schedule changes what it does today
    connection = op.get_bind()
    windowed = connection.execute(
        sa.text(
            "SELECT id, season_start_month, season_end_month FROM care_schedules "
            "WHERE season_start_month IS NOT NULL AND season_end_month IS NOT NULL"
        )
    ).fetchall()
    for schedule_id, season_start_month, season_end_month in windowed:
        overrides = {str(month): None for month in list_months_outside(season_start_month, season_end_month)}
        connection.execute(
            sa.text("UPDATE care_schedules SET month_interval_overrides = :overrides WHERE id = :id"),
            {"overrides": json.dumps(overrides), "id": schedule_id},
        )

    with op.batch_alter_table("care_schedules") as batch:
        batch.drop_column("season_end_month")
        batch.drop_column("season_start_month")


def downgrade() -> None:
    op.add_column("care_schedules", sa.Column("season_start_month", sa.Integer(), nullable=True))
    op.add_column("care_schedules", sa.Column("season_end_month", sa.Integer(), nullable=True))

    # a window can only carry "do it" and "do not": a month slowed rather than skipped has nowhere to go here
    # and is dropped, which is exactly the limitation this migration was written to remove
    connection = op.get_bind()
    overridden = connection.execute(
        sa.text("SELECT id, month_interval_overrides FROM care_schedules WHERE month_interval_overrides IS NOT NULL")
    ).fetchall()
    for schedule_id, raw_overrides in overridden:
        overrides = json.loads(raw_overrides) if isinstance(raw_overrides, str) else raw_overrides
        active_months = {month for month in ALL_MONTHS if overrides.get(str(month), "unset") is not None}
        window = derive_window(active_months)
        if window is None:
            continue
        connection.execute(
            sa.text("UPDATE care_schedules SET season_start_month = :start, season_end_month = :end WHERE id = :id"),
            {"start": window[0], "end": window[1], "id": schedule_id},
        )

    with op.batch_alter_table("care_schedules") as batch:
        batch.drop_column("month_interval_overrides")
