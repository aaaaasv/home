"""
What the assistant may look up for itself, instead of being handed everything at once.

the facts gatherers concatenate five modules' records into the system prompt of every single question. that
has two faults and only one of them is size: a year of six sensors will never fit in a prompt, and the five
modules that do fit crowd out the fifteen that never got a gatherer. so the history lives behind tools —
read-only views over the same use cases the family's own cards are built from — and the dump stays for the
short summaries it is actually good at.

the descriptions are the only way the model learns this data exists at all, so they say what the numbers
mean rather than naming columns.
"""

import logging
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from src.bot.formatting import GENITIVE_MONTH_NAMES
from src.common.config import Settings
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork

logger = logging.getLogger(__name__)

MAX_DAYS = 365
AIR_CONDITIONER_RUNS_LIMIT = 60

HOUSEHOLD_TOOLS: list[dict[str, Any]] = [
    {
        "name": "grid_log",
        "description": (
            "Коли в квартирі зникало й з'являлось світло. Кожен рядок — момент і що саме сталось; тривалість "
            "відключення це проміжок між сусідніми рядками. Беріть на будь-яке питання про відключення: "
            "«коли востаннє не було світла», «скільки разів цього тижня», «о котрій зазвичай вимикають». "
            "Записи ведуться з 9 жовтня 2026 — раніше їх ніхто не зберігав, тож старішого нема."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "description": "скільки останніх днів, до 365"}},
            "required": ["days"],
        },
    },
    {
        "name": "room_climate",
        "description": (
            "Погода в кімнатах по днях: мінімум, максимум і середнє для температури й вологості, окремо для "
            "кожної кімнати з датчиком. Беріть на «в якій кімнаті найхолодніше», «чи було душно вночі», "
            "«як змінилось відколи ввімкнули опалення»."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "скільки останніх днів, до 365"},
                "room": {"type": "string", "description": "назва кімнати; без неї — усі"},
            },
            "required": ["days"],
        },
    },
    {
        "name": "outdoor_weather",
        "description": (
            "Погода надворі по днях — те саме, що room_climate, але зовні. Разом із ним відповідає на "
            "питання про тепловтрати: наскільки кімната стигне, коли надворі холоднішає. Записи ведуться з "
            "9 жовтня 2026."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "description": "скільки останніх днів, до 365"}},
            "required": ["days"],
        },
    },
    {
        "name": "air_conditioner_log",
        "description": (
            "Коли вмикався кондиціонер і на скільки. Беріть на «скільки він наробив цього літа», «чи "
            "працював, коли нікого не було вдома»."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "description": "скільки останніх днів, до 365"}},
            "required": ["days"],
        },
    },
    {
        "name": "places",
        "description": (
            "Список місць, куди родина збиралась сходити, і чи вже сходили. Беріть на «куди ми ще не "
            "ходили», «що там у списку на вихідні»."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]


class HouseholdTools:
    """The tool side of one question — read-only, and about this household only."""

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        household_calendar: HouseholdCalendar,
        settings: Settings,
    ):
        self.uow_factory = uow_factory
        self.household_calendar = household_calendar
        self.settings = settings

    @property
    def definitions(self) -> list[dict[str, Any]]:
        return HOUSEHOLD_TOOLS

    async def run(self, name: str, arguments: dict[str, Any]) -> str:
        days = min(int(arguments.get("days", 7)), MAX_DAYS)
        if name == "grid_log":
            return await self.grid_log(days)
        if name == "room_climate":
            return await self.room_climate(days, arguments.get("room"))
        if name == "outdoor_weather":
            return await self.outdoor_weather(days)
        if name == "air_conditioner_log":
            return await self.air_conditioner_log(days)
        if name == "places":
            return await self.places()
        logger.warning("The assistant asked for a tool that does not exist: %s", name)
        return "Такого інструмента немає."

    async def grid_log(self, days: int) -> str:
        async with self.uow_factory() as uow:
            events = await uow.grid_events.list_since(self.household_calendar.now() - timedelta(days=days))
        if not events:
            return "За цей час світло не зникало й не з'являлось — або записів ще немає."
        return "\n".join(
            f"{self._moment(event.at)} · {'світло зникло' if event.state == 'on_battery' else 'світло є'}"
            for event in events
        )

    async def room_climate(self, days: int, room: str | None) -> str:
        until = self.household_calendar.today()
        since = until - timedelta(days=days)
        rooms = [room] if room else sorted(set(self.settings.room_by_sensor.values()))
        sections = []
        for each in rooms:
            async with self.uow_factory() as uow:
                summaries = await uow.sensor_days.list_room_between(each, since, until)
            if not summaries:
                continue
            lines = [f"— {each}:"]
            lines.extend(f"   {_day(summary.day)} · {_climate(summary)}" for summary in summaries)
            sections.append("\n".join(lines))
        return "\n".join(sections) or "Датчики за цей період нічого не записали."

    async def outdoor_weather(self, days: int) -> str:
        until = self.household_calendar.today()
        async with self.uow_factory() as uow:
            days_outside = await uow.outdoor_weather_days.list_between(until - timedelta(days=days), until)
        if not days_outside:
            return "Записів про погоду надворі за цей період немає."
        return "\n".join(f"{_day(outside.day)} · {_climate(outside)}" for outside in days_outside)

    async def air_conditioner_log(self, days: int) -> str:
        async with self.uow_factory() as uow:
            runs = await uow.air_conditioner_runs.list_since(self.household_calendar.now() - timedelta(days=days))
        if not runs:
            return "Кондиціонер за цей період не вмикався."
        return "\n".join(self._run(run) for run in runs[-AIR_CONDITIONER_RUNS_LIMIT:])

    async def places(self) -> str:
        async with self.uow_factory() as uow:
            saved = await uow.places.list_all()
        if not saved:
            return "Список місць порожній."
        return "\n".join(
            f"— {place.name}" + (" · уже були" if place.visited_at else " · ще не були") for place in saved
        )

    def _moment(self, moment) -> str:
        local = moment.astimezone(self.household_calendar.timezone)
        return f"{_day(local.date())} {local:%H:%M}"

    def _run(self, run) -> str:
        if run.ended_at is None:
            return f"{self._moment(run.started_at)} · увімкнений досі"
        minutes = round((run.ended_at - run.started_at).total_seconds() / 60)
        return f"{self._moment(run.started_at)} · {minutes} хв"


def _climate(summary) -> str:
    return f"{_span(summary.minimum_temperature_celsius, summary.maximum_temperature_celsius, '°C')} · " + _span(
        summary.minimum_humidity_percent, summary.maximum_humidity_percent, "%"
    )


def _span(low: float | None, high: float | None, unit: str) -> str:
    if low is None or high is None:
        return "—"
    return f"{low:.0f}–{high:.0f}{unit}"


def _day(day: date) -> str:
    return f"{day.day} {GENITIVE_MONTH_NAMES[day.month - 1]} {day.year}"
