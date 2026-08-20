"""The scheduled job that notices the air conditioner has been running for hours."""
import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from aiogram import Bot

from src.bot.handlers.air_conditioner.formatting import render_air_conditioner_long_run
from src.bot.handlers.air_conditioner.keyboards import build_air_conditioner_stop_keyboard
from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.common.config import Settings
from src.infrastructure.db.uow import UnitOfWork
from src.modules.air_conditioner.services.air_conditioner import AirConditioner
from src.modules.air_conditioner.use_cases.evaluate_air_conditioner_runtime import EvaluateAirConditionerRuntimeUseCase

logger = logging.getLogger(__name__)


class AirConditionerRuntimeJob:
    """
    Speaks only when the unit has been running longer than anyone meant it to, and only once per run.

    the physical remote has the same blind spot: nothing in the flat notices a unit left on over a weekend. a
    message that is normally never sent is exactly what earns a place on the scheduler here.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        weather_topic: ForumTopicRegistry,
        uow_factory: Callable[[], UnitOfWork],
        air_conditioner: AirConditioner,
        settings: Settings,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.weather_topic = weather_topic
        self.uow_factory = uow_factory
        self.air_conditioner = air_conditioner
        self.settings = settings

    async def __call__(self) -> None:
        state = await self.air_conditioner.read_state()
        notice = await EvaluateAirConditionerRuntimeUseCase(
            uow=self.uow_factory(),
            notify_after=timedelta(hours=self.settings.AIR_CONDITIONER_LONG_RUN_HOURS),
        )(state=state, moment=datetime.now(timezone.utc))
        if notice is None:
            return

        await self.bot.send_message(
            chat_id=self.chat_id,
            message_thread_id=await self.weather_topic.resolve(),
            text=render_air_conditioner_long_run(notice),
            reply_markup=build_air_conditioner_stop_keyboard(),
            # the unit left running for hours — a real alert, worth a ping
            disable_notification=False,
        )
        logger.info("Reported the air conditioner running for %s hours", notice.hours)
