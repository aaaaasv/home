from datetime import datetime, timezone


def current_time() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(moment: datetime) -> datetime:
    """Re-attach utc to a moment that arrived without it — a row written this request has not been through
    the column type that puts the offset back, because sqlite keeps none."""
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
