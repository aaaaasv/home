import logging
from collections.abc import Callable
from datetime import datetime, tzinfo

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

from src.bot.handlers.power.formatting import render_outage_outlook
from src.bot.handlers.power.keyboards import build_outage_schedule_keyboard
from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.bot.services.posted_message_tracker import OUTAGE_SCHEDULE_KIND, PostedMessageTracker
from src.infrastructure.db.uow import UnitOfWork
from src.modules.power.domain import OutageOutlook
from src.modules.power.services.outage_schedule_provider import OutageScheduleProvider

logger = logging.getLogger(__name__)

# a bot may edit its own message for 48h; past that the day's board is reposted rather than left stale
UNEDITABLE_MESSAGE_ERRORS = ("message to edit not found", "message can't be edited", "message_id_invalid")


class OutageScheduleBoard:
    """
    The outage schedule as one self-editing message: posted while an outage is still ahead, kept current in place,
    and silent — a glance, never a ping. it posts NOTHING on a clear day (the shopping-list rule: a board earns a
    scheduled message only if that message is usually empty), and clears itself the moment a planned day turns clear.

    it carries both published days, because yasno may publish a day's intervals at any hour: on 7 october they
    landed at 21:10, and a board about today alone had nothing left to tell anybody.

    `notify` exists for exactly one event: the group turning to emergency shutdowns. that used to be a separate
    push, which meant two messages a minute apart saying the same sentence — the board already carries the
    banner. so the regime announces itself by reposting the board with a ping instead.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        power_topic: ForumTopicRegistry,
        uow_factory: Callable[[], UnitOfWork],
        schedule_provider: OutageScheduleProvider,
        timezone: tzinfo,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.power_topic = power_topic
        self.uow_factory = uow_factory
        self.schedule_provider = schedule_provider
        self.timezone = timezone
        self.tracker = PostedMessageTracker(bot=bot, uow_factory=uow_factory)

    async def post(self, outlook: OutageOutlook | None = None, notify: bool = False) -> Message | None:
        outlook = outlook if outlook is not None else await self.schedule_provider.fetch()
        now = datetime.now(self.timezone)
        # nothing left to say → make sure no stale board lingers from earlier, then stay silent
        if outlook is None or not outlook.has_anything_ahead(now):
            await self.tracker.clear(OUTAGE_SCHEDULE_KIND)
            return None

        await self.tracker.clear(OUTAGE_SCHEDULE_KIND)
        message = await self.bot.send_message(
            chat_id=self.chat_id,
            message_thread_id=await self.power_topic.resolve(),
            text=render_outage_outlook(outlook, now),
            reply_markup=build_outage_schedule_keyboard(),
            # a glance, not a call to action — the daily board is delivered and refreshed without a ping
            disable_notification=not notify,
        )
        await self.tracker.remember(OUTAGE_SCHEDULE_KIND, message)
        logger.info("Posted the outage schedule for %s and the day after", outlook.today.day.isoformat())
        return message

    async def refresh(self, outlook: OutageOutlook | None = None) -> bool:
        message_id = await self._remembered_message_id()
        if message_id is None:
            # nothing on the board yet — the daily post owns first publication, not a silent refresh
            return False

        outlook = outlook if outlook is not None else await self.schedule_provider.fetch()
        now = datetime.now(self.timezone)
        if outlook is None or not outlook.has_anything_ahead(now):
            # the planned day turned clear, or played out with nothing published for tomorrow — drop the board
            await self.tracker.clear(OUTAGE_SCHEDULE_KIND)
            return True

        try:
            await self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=message_id,
                text=render_outage_outlook(outlook, now),
                reply_markup=build_outage_schedule_keyboard(),
            )
        except TelegramBadRequest as error:
            reason = str(error).lower()
            if "message is not modified" in reason:
                return True
            if not any(uneditable in reason for uneditable in UNEDITABLE_MESSAGE_ERRORS):
                raise
            # older than 48h — repost fresh so the topic keeps a live board
            await self.post(outlook)
        return True

    async def _remembered_message_id(self) -> int | None:
        async with self.uow_factory() as uow:
            posted = await uow.posted_messages.list_by_kind(OUTAGE_SCHEDULE_KIND)
        return posted[-1].message_id if posted else None
