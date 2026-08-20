import logging
from collections.abc import Callable
from datetime import datetime, tzinfo

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from src.bot.handlers.power.formatting import render_outage_schedule
from src.bot.handlers.power.keyboards import build_outage_schedule_keyboard
from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.bot.services.posted_message_tracker import OUTAGE_SCHEDULE_KIND, PostedMessageTracker
from src.infrastructure.db.uow import UnitOfWork
from src.modules.power.services.yasno_schedule_provider import OutageSchedule, YasnoScheduleProvider

logger = logging.getLogger(__name__)

# a bot may edit its own message for 48h; past that the day's board is reposted rather than left stale
UNEDITABLE_MESSAGE_ERRORS = ("message to edit not found", "message can't be edited", "message_id_invalid")


class OutageScheduleBoard:
    """
    The outage schedule as one self-editing message: posted the day an outage is planned, kept current in place,
    and silent — a glance, never a ping. it posts NOTHING on a clear day (the shopping-list rule: a board earns a
    scheduled message only if that message is usually empty), and clears itself the moment a planned day turns clear.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        power_topic: ForumTopicRegistry,
        uow_factory: Callable[[], UnitOfWork],
        schedule_provider: YasnoScheduleProvider,
        timezone: tzinfo,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.power_topic = power_topic
        self.uow_factory = uow_factory
        self.schedule_provider = schedule_provider
        self.timezone = timezone
        self.tracker = PostedMessageTracker(bot=bot, uow_factory=uow_factory)

    async def post(self, schedule: OutageSchedule | None = None) -> None:
        schedule = schedule if schedule is not None else await self.schedule_provider.fetch_today()
        # nothing to say → make sure no stale board lingers from earlier, then stay silent
        if schedule is None or not schedule.has_outages:
            await self.tracker.clear(OUTAGE_SCHEDULE_KIND)
            return

        await self.tracker.clear(OUTAGE_SCHEDULE_KIND)
        message = await self.bot.send_message(
            chat_id=self.chat_id,
            message_thread_id=await self.power_topic.resolve(),
            text=render_outage_schedule(schedule, datetime.now(self.timezone)),
            reply_markup=build_outage_schedule_keyboard(),
            # a glance, not a call to action — the pushes are separate; deliver and refresh this without a ping
            disable_notification=True,
        )
        await self.tracker.remember(OUTAGE_SCHEDULE_KIND, message)
        logger.info("Posted the outage schedule with %s interval(s)", len(schedule.off_intervals))

    async def refresh(self, schedule: OutageSchedule | None = None) -> bool:
        message_id = await self._remembered_message_id()
        if message_id is None:
            # nothing on the board yet — the daily post owns first publication, not a silent refresh
            return False

        schedule = schedule if schedule is not None else await self.schedule_provider.fetch_today()
        if schedule is None or not schedule.has_outages:
            # the planned day turned clear — drop the board rather than leave an empty one up
            await self.tracker.clear(OUTAGE_SCHEDULE_KIND)
            return True

        try:
            await self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=message_id,
                text=render_outage_schedule(schedule, datetime.now(self.timezone)),
                reply_markup=build_outage_schedule_keyboard(),
            )
        except TelegramBadRequest as error:
            reason = str(error).lower()
            if "message is not modified" in reason:
                return True
            if not any(uneditable in reason for uneditable in UNEDITABLE_MESSAGE_ERRORS):
                raise
            # older than 48h — repost fresh so the topic keeps a live board
            await self.post(schedule)
        return True

    async def _remembered_message_id(self) -> int | None:
        async with self.uow_factory() as uow:
            posted = await uow.posted_messages.list_by_kind(OUTAGE_SCHEDULE_KIND)
        return posted[-1].message_id if posted else None
