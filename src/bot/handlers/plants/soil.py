"""Writing down a watering the probe saw, and saying so where every other care record is said."""
import logging
from collections.abc import Callable

from aiogram import Bot

from src.bot.handlers.plants.formatting import render_recorded_care
from src.bot.handlers.plants.keyboards import build_recorded_care_keyboard
from src.bot.handlers.plants.messages import SOIL_WATERING_DETECTED
from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.common.config import Settings
from src.common.constants import CareTaskType
from src.common.exceptions import DomainError, RecentCareExistsError
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.commands import RecordCareEventCommand
from src.modules.plant_care.use_cases.record_care_event import RecordCareEventUseCase

logger = logging.getLogger(__name__)


def build_watering_recorder(
    bot: Bot,
    settings: Settings,
    care_topic: ForumTopicRegistry,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
):
    """
    Hand the mqtt side one thing it can call, so it never learns what a chat or a card is.

    the card carries the same «скасувати» a tapped record does, which is the whole safety net here: a probe
    that misreads a repotting as a watering costs one tap, and the person is already looking at the message.
    """

    async def record_watering(plant_id: int) -> None:
        moment = household_calendar.now()
        try:
            record = await RecordCareEventUseCase(
                uow=uow_factory(),
                actor=settings.sensor_actor,
                household_calendar=household_calendar,
                recent_care_guard_hours=settings.RECENT_CARE_GUARD_HOURS,
            )(RecordCareEventCommand(plant_id=plant_id, task_type=CareTaskType.WATERING, performed_at=moment))
        except RecentCareExistsError:
            # somebody already wrote this watering down by hand, minutes ago. the guard exists for exactly
            # this, and a second record of one pour would be worse than no record at all
            logger.info("Plant %s was watered by hand just now — the probe adds nothing", plant_id)
            return
        except DomainError as error:
            logger.warning("Cannot record the watering the probe saw for plant %s: %s", plant_id, error)
            return

        await bot.send_message(
            chat_id=settings.TELEGRAM_REMINDER_CHAT_ID,
            message_thread_id=await care_topic.resolve(),
            text=f"{SOIL_WATERING_DETECTED}\n{render_recorded_care(record, moment, household_calendar)}",
            reply_markup=build_recorded_care_keyboard(plant_id, CareTaskType.WATERING),
        )

    return record_watering
