import re
from datetime import date, timedelta

from src.modules.family.domain import FamilyMember

# a stem of each ukrainian weekday name, in whatever case follows «до»/«у»/«в», mapped to python's weekday() index
WEEKDAY_STEMS: dict[str, int] = {
    "понеділ": 0,
    "вівтор": 1,
    "серед": 2,
    "четвер": 3,
    "пятниц": 4,
    "субот": 5,
    "неділ": 6,
}
RELATIVE_DAYS: dict[str, int] = {"сьогодні": 0, "завтра": 1, "післязавтра": 2}

# only an END-anchored, explicitly-marked phrase is read as a deadline, so «подарунок на 8 березня» keeps its date
# in the title rather than becoming a due date — the false-positive the family would never forgive
ABSOLUTE_PATTERN = re.compile(r"\s+до\s+(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?\s*$", re.IGNORECASE)
RELATIVE_COUNT_PATTERN = re.compile(r"\s+через\s+(\d{1,3})\s+(дн\w*|тижд\w*|тижн\w*)\s*$", re.IGNORECASE)
RELATIVE_WORD_PATTERN = re.compile(r"\s+(?:до\s+)?(сьогодні|завтра|післязавтра)\s*$", re.IGNORECASE)
WEEKDAY_PATTERN = re.compile(r"\s+(?:до|у|в|на)\s+([а-яіїєґʼ'’`]+)\s*$", re.IGNORECASE)
# a leading name — «Марта забрати посилку», «Марта: забрати», «Марта — забрати» — the first token, then the rest
LEADING_NAME_PATTERN = re.compile(r"^\s*([^\s:,—-]+)\s*[:,—-]?\s+(\S.*)$")


def parse_chore_text(text: str, today: date) -> tuple[str, date | None]:
    """Splits a typed chore into its name and an optional deadline, e.g. «забрати негативи до 31.07»"""
    stripped = text.strip()

    absolute = ABSOLUTE_PATTERN.search(stripped)
    if absolute is not None:
        due_on = _absolute_date(absolute, today)
        if due_on is not None:
            return _name_before(stripped, absolute), due_on

    relative_count = RELATIVE_COUNT_PATTERN.search(stripped)
    if relative_count is not None:
        return _name_before(stripped, relative_count), today + _relative_count(relative_count)

    relative_word = RELATIVE_WORD_PATTERN.search(stripped)
    if relative_word is not None:
        return _name_before(stripped, relative_word), today + timedelta(
            days=RELATIVE_DAYS[relative_word.group(1).lower()]
        )

    weekday = WEEKDAY_PATTERN.search(stripped)
    if weekday is not None:
        due_on = _weekday_date(weekday.group(1), today)
        if due_on is not None:
            return _name_before(stripped, weekday), due_on

    return stripped, None


def split_assignee(text: str, members: list[FamilyMember]) -> tuple[FamilyMember | None, str]:
    """Lifts a leading family name off a chore, so «Марта забрати посилку» tags Марта — only a name the bot knows"""
    match = LEADING_NAME_PATTERN.match(text)
    if match is None:
        return None, text.strip()

    candidate = match.group(1).lower()
    for member in members:
        if member.first_name.lower() == candidate:
            return member, match.group(2).strip()
    return None, text.strip()


def parse_deadline(text: str, today: date) -> date | None:
    """Reads a bare date reply for the «дата» menu — the patterns expect a name before the phrase, so give them one"""
    cleaned = text.strip()
    for candidate in (f"дата до {cleaned}", f"дата {cleaned}"):
        _, due_on = parse_chore_text(candidate, today)
        if due_on is not None:
            return due_on
    return None


def _name_before(text: str, match: re.Match) -> str:
    return text[: match.start()].strip(" —-,\t\n")


def _absolute_date(match: re.Match, today: date) -> date | None:
    day, month = int(match.group(1)), int(match.group(2))
    year_group = match.group(3)
    try:
        if year_group is not None:
            year = int(year_group)
            return date(year + 2000 if year < 100 else year, month, day)
        due_on = date(today.year, month, day)
        # a bare day.month already past this year means next year's — nobody schedules into the past
        return due_on if due_on >= today else date(today.year + 1, month, day)
    except ValueError:
        return None


def _relative_count(match: re.Match) -> timedelta:
    amount = int(match.group(1))
    return timedelta(weeks=amount) if match.group(2).lower().startswith("тиж") else timedelta(days=amount)


def _weekday_date(word: str, today: date) -> date | None:
    normalized = re.sub(r"[ʼ'’`]", "", word.lower())
    for stem, weekday in WEEKDAY_STEMS.items():
        if normalized.startswith(stem):
            return today + timedelta(days=(weekday - today.weekday()) % 7)
    return None
