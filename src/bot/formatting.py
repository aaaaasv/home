from datetime import date, datetime, timedelta

from src.common.constants import TELEGRAM_CAPTION_MAX_LENGTH
from src.common.household_calendar import HouseholdCalendar

GENITIVE_MONTH_NAMES = (
    "січня",
    "лютого",
    "березня",
    "квітня",
    "травня",
    "червня",
    "липня",
    "серпня",
    "вересня",
    "жовтня",
    "листопада",
    "грудня",
)


BUTTON_VALUE_MAX_LENGTH = 24


def shorten_for_button(value: str | None) -> str:
    if value is None:
        return "—"
    if len(value) <= BUTTON_VALUE_MAX_LENGTH:
        return value
    return value[: BUTTON_VALUE_MAX_LENGTH - 1].rstrip() + "…"


def format_runtime(minutes: int) -> str:
    """Hours and minutes the way the family says them — the shape every battery, outage and alert span uses."""
    hours, remaining_minutes = divmod(minutes, 60)
    if hours and remaining_minutes:
        return f"{hours} год {remaining_minutes} хв"
    if hours:
        return f"{hours} год"
    return f"{remaining_minutes} хв"


def format_duration(duration: timedelta) -> str:
    return format_runtime(round(duration.total_seconds() / 60))


def format_span(span: timedelta) -> str:
    """
    A stretch of time as the family would say it out loud, up to days.

    this is not `format_runtime`: a station's runtime is hours at most, while the light is routinely on for
    days between outages, and "76 год 15 хв" is not an answer anybody reads.
    """
    minutes = max(round(span.total_seconds() / 60), 0)
    days, minutes_of_day = divmod(minutes, 24 * 60)
    hours, remaining_minutes = divmod(minutes_of_day, 60)
    if days:
        return f"{days} {_days_word(days)} {hours} год" if hours else f"{days} {_days_word(days)}"
    return format_runtime(minutes_of_day) if (hours or remaining_minutes) else "менше хвилини"


def _days_word(days: int) -> str:
    # 1 день, 2-4 дні, 5-20 днів, 21 день, 22-24 дні — the teens are all "днів"
    if days % 10 == 1 and days % 100 != 11:
        return "день"
    if days % 10 in (2, 3, 4) and days % 100 not in (12, 13, 14):
        return "дні"
    return "днів"


def pluralize_days(count: int) -> str:
    if 11 <= count % 100 <= 14:
        return f"{count} днів"
    if count % 10 == 1:
        return f"{count} день"
    if 2 <= count % 10 <= 4:
        return f"{count} дні"
    return f"{count} днів"


def format_day(day: date, today: date) -> str:
    formatted = f"{day.day} {GENITIVE_MONTH_NAMES[day.month - 1]}"
    if day.year != today.year:
        return f"{formatted} {day.year}"
    return formatted


def format_moment(moment: datetime, calendar: HouseholdCalendar) -> str:
    local_moment = moment.astimezone(calendar.timezone)
    return f"{format_day(local_moment.date(), calendar.today())}, {local_moment:%H:%M}"


def format_due(days_until_due: int) -> str:
    if days_until_due < 0:
        return f"прострочено {pluralize_days(-days_until_due)}"
    if days_until_due == 0:
        return "сьогодні"
    if days_until_due == 1:
        return "завтра"
    return f"через {pluralize_days(days_until_due)}"


def exceeds_caption_limit(text: str) -> bool:
    # telegram counts utf-16 code units, so an emoji outside the bmp costs two
    return len(text.encode("utf-16-le")) // 2 > TELEGRAM_CAPTION_MAX_LENGTH
