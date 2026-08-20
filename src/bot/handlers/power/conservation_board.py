import logging
from collections.abc import Callable
from datetime import datetime, tzinfo

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from src.bot.handlers.power.formatting import render_conservation_card
from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.bot.services.posted_message_tracker import CONSERVATION_CARD_KIND, PostedMessageTracker
from src.infrastructure.db.uow import UnitOfWork
from src.modules.power.services.conservation import (
    ConservationKind,
    ConservationLevel,
    ConservationMode,
    ConservationState,
    evaluate,
)

logger = logging.getLogger(__name__)

CONSERVATION_LEVEL_RANK = {
    ConservationLevel.GREEN: 0,
    ConservationLevel.BLUE: 1,
    ConservationLevel.YELLOW: 2,
    ConservationLevel.RED: 3,
}


class ConservationBoard:
    """
    The shelved station's storage card: one standing message, silent while nothing needs doing, a ping the first
    time the charge crosses into a state that wants action (and every day while the warranty deadline nears),
    dropped the moment the station goes back into use. refreshed on a schedule, and again the instant someone marks
    the state by hand from /eco — so a manual "на зберігання" shows its card immediately, not on the next tick.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        power_topic: ForumTopicRegistry,
        uow_factory: Callable[[], UnitOfWork],
        timezone: tzinfo,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.power_topic = power_topic
        self.uow_factory = uow_factory
        self.timezone = timezone
        self.tracker = PostedMessageTracker(bot=bot, uow_factory=uow_factory)

    async def refresh(self) -> None:
        now = datetime.now(self.timezone)
        async with self.uow_factory() as uow:
            record = await uow.conservation.get()
            previous_level = record.last_advised_level if record is not None else None
            if record is None or not record.is_conserved:
                advisory = None
            else:
                advisory = evaluate(
                    ConservationState(
                        stored_percent=record.stored_percent,
                        stored_at=record.stored_at,
                        mode=ConservationMode(record.mode),
                        last_cycle_at=record.last_cycle_at,
                    ),
                    now,
                )

        if advisory is None:
            await self.tracker.clear(CONSERVATION_CARD_KIND)
            if previous_level is not None:
                await self._remember_level(None)
            return

        await self._deliver(advisory, previous_level)
        await self._remember_level(advisory.level.value)

    async def _deliver(self, advisory, previous_level) -> None:
        text = render_conservation_card(advisory)
        if not self._should_ping(advisory, previous_level):
            # a steady state — rewrite the standing card in place, silently
            message_id = await self._remembered_message_id()
            if message_id is not None:
                try:
                    await self.bot.edit_message_text(chat_id=self.chat_id, message_id=message_id, text=text)
                    return
                except TelegramBadRequest as error:
                    # unchanged text needs no rewrite; anything else falls through to a fresh (silent) card
                    if "message is not modified" in str(error).lower():
                        return

        # a fresh crossing into action (or a card that could not be edited) — repost so it can ping, or first publish
        await self.tracker.clear(CONSERVATION_CARD_KIND)
        posted = await self.bot.send_message(
            chat_id=self.chat_id,
            message_thread_id=await self.power_topic.resolve(),
            text=text,
            disable_notification=not self._should_ping(advisory, previous_level),
        )
        await self.tracker.remember(CONSERVATION_CARD_KIND, posted)

    def _should_ping(self, advisory, previous_level) -> bool:
        if advisory.level not in (ConservationLevel.YELLOW, ConservationLevel.RED):
            return False
        # the warranty deadline nags every day; other actionable states ping only on the first crossing up into them
        if advisory.kind == ConservationKind.WARRANTY:
            return True
        if previous_level is None:
            return True
        return CONSERVATION_LEVEL_RANK[advisory.level] > CONSERVATION_LEVEL_RANK.get(
            ConservationLevel(previous_level), -1
        )

    async def _remembered_message_id(self) -> int | None:
        async with self.uow_factory() as uow:
            posted = await uow.posted_messages.list_by_kind(CONSERVATION_CARD_KIND)
        return posted[-1].message_id if posted else None

    async def _remember_level(self, level: str | None) -> None:
        async with self.uow_factory() as uow:
            if await uow.conservation.get() is not None:
                await uow.conservation.save({"last_advised_level": level})
