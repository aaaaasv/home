from datetime import date, datetime

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
