from datetime import date, datetime, timezone
from typing import Any

from src.common.constants import CareTaskType
from src.common.domain import Actor

OWNER = Actor(telegram_user_id=42, display_name="Богдан")
PARTNER = Actor(telegram_user_id=99, display_name="Марта")


def build_plant_payload(
    name: str = "Монстера",
    species: str | None = "Monstera deliciosa",
    location: str | None = "вітальня",
    notes: str | None = None,
    added_by_telegram_user_id: int = OWNER.telegram_user_id,
    is_archived: bool = False,
    **overrides: Any,
) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "name": name,
        "species": species,
        "location": location,
        "notes": notes,
        "added_by_telegram_user_id": added_by_telegram_user_id,
        "is_archived": is_archived,
    }
    return {**defaults, **overrides}


def build_care_schedule_payload(
    plant_id: int,
    task_type: CareTaskType = CareTaskType.WATERING,
    interval_days: int = 7,
    next_due_on: date | None = None,
    last_performed_at: datetime | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "plant_id": plant_id,
        "task_type": task_type,
        "interval_days": interval_days,
        "next_due_on": next_due_on or date(2026, 7, 12),
        "last_performed_at": last_performed_at,
    }
    return {**defaults, **overrides}


def build_care_event_payload(
    plant_id: int,
    task_type: CareTaskType = CareTaskType.WATERING,
    performed_at: datetime | None = None,
    performed_by: Actor = OWNER,
    note: str | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "plant_id": plant_id,
        "task_type": task_type,
        "performed_at": performed_at or datetime(2026, 7, 5, 9, 0, tzinfo=timezone.utc),
        "performed_by_telegram_user_id": performed_by.telegram_user_id,
        "performed_by_display_name": performed_by.display_name,
        "note": note,
    }
    return {**defaults, **overrides}


def build_plant_photo_payload(
    plant_id: int,
    telegram_file_id: str = "file-1",
    telegram_file_unique_id: str = "unique-1",
    local_path: str | None = None,
    caption: str | None = None,
    added_by_telegram_user_id: int = OWNER.telegram_user_id,
    taken_at: datetime | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "plant_id": plant_id,
        "telegram_file_id": telegram_file_id,
        "telegram_file_unique_id": telegram_file_unique_id,
        "local_path": local_path,
        "caption": caption,
        "added_by_telegram_user_id": added_by_telegram_user_id,
        "taken_at": taken_at or datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
    }
    return {**defaults, **overrides}
