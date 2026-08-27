"""The scheduled job that speaks when everyone has left and the air conditioner has not."""
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.bot.handlers.air_conditioner.keyboards import build_air_conditioner_stop_keyboard
from src.bot.handlers.presence.messages import PRESENCE_EVERYONE_LEFT_AC_ON
from src.bot.scheduling import SchedulerContext
from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.common.config import Settings
from src.modules.air_conditioner.services.air_conditioner import AirConditioner
from src.modules.presence.monitor import PresenceMonitor
from src.modules.presence.services.presence_source import PresenceSource

logger = logging.getLogger(__name__)


class PresenceJob:
    """
    Watches whether any family phone is still on Wi-Fi and speaks only at the moment the last one leaves while the
    air conditioner is still running — the blind spot the physical remote shares. it stays silent otherwise.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        weather_topic: ForumTopicRegistry,
        presence_source: PresenceSource,
        air_conditioner: AirConditioner,
        settings: Settings,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.weather_topic = weather_topic
        self.presence_source = presence_source
        self.air_conditioner = air_conditioner
        self.monitor = PresenceMonitor(
            family_macs=settings.presence_phone_macs,
            away_grace=timedelta(minutes=settings.PRESENCE_AWAY_GRACE_MINUTES),
        )

    async def __call__(self) -> None:
        online = await self.presence_source.online_macs()
        if online is None:
            return
        if not self.monitor.update(online, datetime.now(timezone.utc)):
            return

        state = await self.air_conditioner.read_state()
        if state is None or not state.is_on:
            return

        await self.bot.send_message(
            chat_id=self.chat_id,
            message_thread_id=await self.weather_topic.resolve(),
            text=PRESENCE_EVERYONE_LEFT_AC_ON,
            reply_markup=build_air_conditioner_stop_keyboard(),
            # everyone left the flat with the AC running — the ping is the whole point
            disable_notification=False,
        )
        logger.info("Everyone left with the air conditioner still on")


def register_jobs(scheduler: AsyncIOScheduler, context: SchedulerContext) -> None:
    """Watch the roster of phones on the wi-fi — pointless without a unit to catch running in an empty flat."""
    settings = context.settings
    if (
        not settings.PRESENCE_ENABLED
        or context.weather_topic is None
        or context.presence_source is None
        or context.air_conditioner is None
    ):
        return

    presence_job = PresenceJob(
        bot=context.bot,
        chat_id=settings.TELEGRAM_REMINDER_CHAT_ID,
        weather_topic=context.weather_topic,
        presence_source=context.presence_source,
        air_conditioner=context.air_conditioner,
        settings=settings,
    )
    scheduler.add_job(
        presence_job.__call__,
        trigger=IntervalTrigger(minutes=settings.PRESENCE_CHECK_MINUTES),
        id="presence",
        replace_existing=True,
    )
