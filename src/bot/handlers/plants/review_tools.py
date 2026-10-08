"""
What the photo review may look up for itself, on top of what it is handed.

the review is given two frames and the plant's record, which answers most questions. the rest of what this
house knows — every earlier frame, the care log, the room's weather — used to be unreachable, so a model that
needed it could only guess or hedge. these are read-only views over the same use cases the family's own cards
are built from, so nothing here can tell the model something the herbarium sheet would not.

the descriptions matter as much as the data: they are the only way the model learns that any of this exists.
"""

import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from src.bot.formatting import GENITIVE_MONTH_NAMES
from src.bot.handlers.plants.messages import CARE_TASK_LABELS
from src.common.constants import CareTaskType
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.adapters.image_encoding import read_image_base64
from src.infrastructure.db.uow import UnitOfWork

logger = logging.getLogger(__name__)

CARE_EVENTS_LIMIT = 40
# a day either side of the pair is not worth a round trip; months are
CLIMATE_DAYS_LIMIT = 120

REVIEW_TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_photos",
        "description": (
            "Усі збережені знімки цієї рослини з датами. Кадри бувають двох ґатунків: overview — загальний "
            "план, по одному з кожної зйомки, саме їх порівнюють між собою; detail — крупний план листка чи "
            "ґрунту, знятий того ж дня. Поверни цей список, якщо треба зазирнути глибше за ті два кадри, що "
            "тобі дали: наприклад подивитись, як рослина виглядала три місяці тому, або знайти крупний план "
            "того самого дня."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "view_photo",
        "description": (
            "Показати один збережений знімок за його id зі списку list_photos. Можна кликати кілька разів."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"photo_id": {"type": "integer", "description": "id зі списку list_photos"}},
            "required": ["photo_id"],
        },
    },
    {
        "name": "care_log",
        "description": (
            "Що насправді робили з цією рослиною і коли: полив, підживлення, промивання, пересадка, "
            "обрізка — з датою, хто робив і нотаткою, якщо лишили. Розклад каже, як мало б бути; цей журнал "
            "каже, як було. Беріть його, коли підозрюєте, що проміжки між доглядом нерівні."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "room_climate",
        "description": (
            "Погода в кімнаті цієї рослини по днях: мінімум, максимум і середнє для температури й вологості. "
            "Дані з датчика саме її кімнати, не з іншої. Беріть, коли треба заглянути далі, ніж проміжок між "
            "двома наданими знімками — наприклад перевірити, чи був сухий тиждень місяць тому."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": f"скільки останніх днів показати, до {CLIMATE_DAYS_LIMIT}",
                }
            },
            "required": ["days"],
        },
    },
]


class PlantReviewTools:
    """The tool side of one review: everything it may look up is about this one plant."""

    def __init__(self, plant_id: int, uow_factory: Callable[[], UnitOfWork], household_calendar: HouseholdCalendar):
        self.plant_id = plant_id
        self.uow_factory = uow_factory
        self.household_calendar = household_calendar

    async def run(self, name: str, arguments: dict[str, Any]) -> list[dict[str, Any]] | str:
        if name == "list_photos":
            return await self.list_photos()
        if name == "view_photo":
            return await self.view_photo(int(arguments["photo_id"]))
        if name == "care_log":
            return await self.care_log()
        if name == "room_climate":
            return await self.room_climate(int(arguments["days"]))
        logger.warning("The review asked for a tool that does not exist: %s", name)
        return "Такого інструмента немає."

    async def list_photos(self) -> str:
        async with self.uow_factory() as uow:
            photos = await uow.plant_photos.list_by_plant_id(self.plant_id)
        if not photos:
            return "Збережених знімків немає."
        return "\n".join(
            f"id={photo.id} · {_format_day(self.household_calendar.local_date(photo.taken_at))} · {photo.frame}"
            + (f" · підпис: {photo.caption}" if photo.caption else "")
            for photo in photos
        )

    async def view_photo(self, photo_id: int) -> list[dict[str, Any]] | str:
        async with self.uow_factory() as uow:
            photo = await uow.plant_photos.retrieve(photo_id)
        if photo is None or photo.plant_id != self.plant_id:
            return "Такого знімка в цієї рослини немає."
        if not photo.local_path:
            return "Цей знімок не зберігся на диску."
        try:
            encoded = read_image_base64(photo.local_path)
        except OSError:
            logger.warning("The review asked for photo %s, which is gone from disk", photo_id)
            return "Файл цього знімка не читається."
        taken_on = _format_day(self.household_calendar.local_date(photo.taken_at))
        return [
            {"type": "text", "text": f"Знімок id={photo.id}, {taken_on}:"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": encoded}},
        ]

    async def care_log(self) -> str:
        async with self.uow_factory() as uow:
            events = await uow.care_events.list_recent_by_plant_id(self.plant_id, CARE_EVENTS_LIMIT)
        if not events:
            return "Доглядових записів немає."
        return "\n".join(
            f"{_format_day(self.household_calendar.local_date(event.performed_at))} · "
            f"{CARE_TASK_LABELS[CareTaskType(event.task_type)]} · {event.performed_by_display_name}"
            + (f" · {event.note}" if event.note else "")
            for event in events
        )

    async def room_climate(self, days: int) -> str:
        async with self.uow_factory() as uow:
            plant = await uow.plants.retrieve_active(self.plant_id)
            if plant is None or not plant.room:
                return "У цієї рослини не вказана кімната, тож погоди по ній немає."
            until = self.household_calendar.today()
            since = until - timedelta(days=min(days, CLIMATE_DAYS_LIMIT))
            summaries = await uow.sensor_days.list_room_between(plant.room, since, until)
        if not summaries:
            return "Датчик цієї кімнати за цей період нічого не записав."
        return "\n".join(_render_climate_day(summary) for summary in summaries if _has_temperature(summary))


def _render_climate_day(summary) -> str:
    temperature = _span(summary.minimum_temperature_celsius, summary.maximum_temperature_celsius, "°C")
    humidity = _span(summary.minimum_humidity_percent, summary.maximum_humidity_percent, "%")
    return f"{_format_day(summary.day)} · {temperature} · {humidity}"


def _has_temperature(summary) -> bool:
    return summary.minimum_temperature_celsius is not None


def _span(low: float | None, high: float | None, unit: str) -> str:
    if low is None or high is None:
        return "—"
    return f"{low:.0f}–{high:.0f}{unit}"


def _format_day(day: date | datetime) -> str:
    return f"{day.day} {GENITIVE_MONTH_NAMES[day.month - 1]} {day.year}"
