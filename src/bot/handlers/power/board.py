"""The one board in ⚡ світло: what the flat runs on, and the hours the city plans to take."""
import logging
from collections.abc import Callable
from datetime import datetime, tzinfo

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

from src.bot.handlers.power.formatting import render_power_board
from src.bot.handlers.power.keyboards import build_power_board_keyboard
from src.bot.handlers.power.reserve_readout import ReserveReadout
from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.bot.services.posted_message_tracker import POWER_BOARD_KIND, PostedMessageTracker
from src.infrastructure.db.uow import UnitOfWork
from src.modules.power.domain import DeclaredSupply, OutageOutlook, Reserve
from src.modules.power.services.outage_schedule_provider import OutageScheduleProvider

logger = logging.getLogger(__name__)

# a bot may edit its own message for 48h; past that the board is reposted rather than left stale
UNEDITABLE_MESSAGE_ERRORS = ("message to edit not found", "message can't be edited", "message_id_invalid")


class PowerBoard:
    """
    One standing, self-editing message holding both halves of «коли буде світло».

    it never notifies. the messages that wake the family are the mains pushes, and this is what they come
    here to read afterwards; a board that pinged on every edit would get the whole topic muted, and a muted
    topic takes those pushes down with it. `/eco` deliberately stays separate: it carries buttons that act,
    and those cannot live on a message that is rewritten for weeks.

    **the schedule is remembered, not fetched here.** the minute this card matters most is the minute the
    internet may be gone too, and on battery it is redrawn every tick — asking yasno that often would be
    both rude and useless. whoever has a reason to ask calls `read_outlook`.

    the one ping it ever sends is a repost: when the group goes onto emergency shutdowns, the banner is on
    this card already, so the card is what announces it.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        power_topic: ForumTopicRegistry,
        uow_factory: Callable[[], UnitOfWork],
        timezone: tzinfo,
        reserve_readout: ReserveReadout | None = None,
        schedule_provider: OutageScheduleProvider | None = None,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.power_topic = power_topic
        self.uow_factory = uow_factory
        self.timezone = timezone
        self.reserve_readout = reserve_readout
        self.schedule_provider = schedule_provider
        self.tracker = PostedMessageTracker(bot=bot, uow_factory=uow_factory)
        self._outlook: OutageOutlook | None = None

    @property
    def draws_the_reserve(self) -> bool:
        """Whether this board has a half that moves minute to minute, which is what decides its cadence."""
        return self.reserve_readout is not None

    async def read_reserve(self) -> Reserve | None:
        """None where there is nothing to read: a flat without the hat and the station draws no layers."""
        if self.reserve_readout is None:
            return None
        return await self.reserve_readout.compose()

    async def read_outlook(self) -> OutageOutlook | None:
        """Ask yasno and keep the answer — a fetch that fails leaves the last one standing, which is the point."""
        if self.schedule_provider is None:
            return None
        outlook = await self.schedule_provider.fetch()
        if outlook is not None:
            self._outlook = outlook
        return outlook

    async def post(self, reserve: Reserve | None = None, notify: bool = False) -> Message | None:
        """Move the board to the bottom of the topic, where whoever asked for it is already looking."""
        reserve = reserve if reserve is not None else await self.read_reserve()
        now = datetime.now(self.timezone)
        text = render_power_board(reserve, self._outlook, now)
        if not text:
            # nothing to say at all → make sure no stale board lingers from earlier, then stay silent
            await self.tracker.clear(POWER_BOARD_KIND)
            return None

        await self.tracker.clear(POWER_BOARD_KIND)
        message = await self.bot.send_message(
            chat_id=self.chat_id,
            message_thread_id=await self.power_topic.resolve(),
            text=text,
            reply_markup=build_power_board_keyboard(_declared(reserve)),
            # a glance, not a call to action — the board is delivered and refreshed without a ping
            disable_notification=not notify,
        )
        await self.tracker.remember(POWER_BOARD_KIND, message)
        logger.info("Posted the power board, grid %s", reserve.grid.value if reserve is not None else "unknown")
        return message

    async def refresh(self, reserve: Reserve | None = None) -> bool:
        """Rewrite the standing board in place; False when there is none yet, so the caller can publish the first."""
        message_id = await self._remembered_message_id()
        if message_id is None:
            return False

        reserve = reserve if reserve is not None else await self.read_reserve()
        now = datetime.now(self.timezone)
        text = render_power_board(reserve, self._outlook, now)
        if not text:
            await self.tracker.clear(POWER_BOARD_KIND)
            return True

        try:
            await self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=message_id,
                text=text,
                reply_markup=build_power_board_keyboard(_declared(reserve)),
            )
        except TelegramBadRequest as error:
            reason = str(error).lower()
            if "message is not modified" in reason:
                return True
            if not any(uneditable in reason for uneditable in UNEDITABLE_MESSAGE_ERRORS):
                raise
            # older than 48h — repost fresh so the topic keeps a live board
            await self.post(reserve)
        return True

    async def draw(self, reserve: Reserve | None = None) -> None:
        """Keep the board current: edit it where it stands, or publish the first one."""
        if not await self.refresh(reserve):
            await self.post(reserve)

    def remember(self, outlook: OutageOutlook) -> None:
        self._outlook = outlook

    async def _remembered_message_id(self) -> int | None:
        async with self.uow_factory() as uow:
            posted = await uow.posted_messages.list_by_kind(POWER_BOARD_KIND)
        return posted[-1].message_id if posted else None


def _declared(reserve: Reserve | None) -> DeclaredSupply:
    """A flat with no reserve half to read is a flat with nothing to declare about."""
    return reserve.declared_supply if reserve is not None else DeclaredSupply.GRID
