import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta, tzinfo
from typing import TYPE_CHECKING

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from src.bot.handlers.transit.formatting import render_transit_card
from src.bot.handlers.transit.keyboards import build_transit_keyboard
from src.bot.handlers.transit.messages import TRANSIT_LOOKING
from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.bot.services.posted_message_tracker import TRANSIT_CARD_KIND, PostedMessageTracker
from src.infrastructure.db.uow import UnitOfWork

if TYPE_CHECKING:
    # another track fills its body; the board only depends on the async __call__() -> TransitReport contract
    from src.modules.transit.use_cases.compose_transit_report import ComposeTransitReportUseCase

logger = logging.getLogger(__name__)

TRANSIT_MODULE_NAME = "transit"

# a bot may edit its own message for 48h; past that the card is reposted rather than left stale
UNEDITABLE_MESSAGE_ERRORS = ("message to edit not found", "message can't be edited", "message_id_invalid")


class TransitBoard:
    """
    The «коли наступний» arrival card as one self-editing message: born on /bus as a placeholder, edited into the
    live estimate, then kept current in place for a short window (~5 min, while someone gets ready) before it
    freezes. transit is not «зазвичай порожній», so the card is on-demand and never a daily push — the window is
    an asyncio task that polls the feed only while it is open, and 🔄 reopens a frozen one. every send is silent.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        transit_topic: ForumTopicRegistry,
        uow_factory: Callable[[], UnitOfWork],
        compose_transit_report: "ComposeTransitReportUseCase",
        timezone: tzinfo,
        refresh_interval: timedelta,
        refresh_window: timedelta,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.transit_topic = transit_topic
        self.uow_factory = uow_factory
        self.compose_transit_report = compose_transit_report
        self.timezone = timezone
        self.refresh_interval = refresh_interval
        self.refresh_window = refresh_window
        self.tracker = PostedMessageTracker(bot=bot, uow_factory=uow_factory)
        self._refresh_task: asyncio.Task | None = None

    async def post(self) -> None:
        # replace any earlier card so only the newest one is live, then show a placeholder before the first estimate
        await self._cancel_refresh_window()
        await self.tracker.clear(TRANSIT_CARD_KIND)
        placeholder = await self.bot.send_message(
            chat_id=self.chat_id,
            message_thread_id=await self.transit_topic.resolve(),
            text=TRANSIT_LOOKING,
            # a card someone opens themselves, refreshed in place — deliver and update it without a ping
            disable_notification=True,
        )
        await self.tracker.remember(TRANSIT_CARD_KIND, placeholder)
        await self._refresh_once()
        self._start_refresh_window()

    async def resume(self) -> None:
        # the 🔄 button on a frozen card: refresh in place and reopen the window; an uneditable card starts fresh
        if await self._remembered_message_id() is None:
            await self.post()
            return

        await self._cancel_refresh_window()
        if await self._refresh_once():
            # the card had aged past 48h; _refresh_once reposted it, and post reopened its own window
            return
        self._start_refresh_window()

    async def stop(self) -> None:
        await self._cancel_refresh_window()

    async def _refresh_once(self, is_live: bool = True) -> bool:
        """Renders the current estimate over the card in place; returns True only if it had to repost a stale card"""
        message_id = await self._remembered_message_id()
        if message_id is None:
            return False

        report = await self.compose_transit_report()
        text = render_transit_card(report, generated_at=datetime.now(self.timezone), is_live=is_live)
        try:
            await self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=message_id,
                text=text,
                reply_markup=build_transit_keyboard(),
            )
        except TelegramBadRequest as error:
            reason = str(error).lower()
            if "message is not modified" in reason:
                return False
            if not any(uneditable in reason for uneditable in UNEDITABLE_MESSAGE_ERRORS):
                raise
            # older than 48h — repost fresh so the topic keeps a live card (never reached mid-window: it is minutes old)
            await self.post()
            return True
        return False

    async def _run_refresh_window(self) -> None:
        deadline = asyncio.get_running_loop().time() + self.refresh_window.total_seconds()
        try:
            while asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(self.refresh_interval.total_seconds())
                await self._refresh_once()
        except asyncio.CancelledError:
            # a newer card is taking over — it owns the message now, so leave the footer to it
            raise
        except Exception:
            # any other failure ends the loop, and the card would keep its «оновлюється» footer while
            # nothing refreshes it — a stale card that still looks live is the one thing to avoid
            logger.exception("The transit refresh window stopped early, freezing the card")

        self._refresh_task = None
        try:
            await self._freeze()
        except Exception:
            logger.exception("Could not freeze the transit card")

    async def _freeze(self) -> None:
        # the window is over — one last edit that swaps the live footer for the frozen «🔄 щоб оновити» one
        await self._refresh_once(is_live=False)

    def _start_refresh_window(self) -> None:
        self._refresh_task = asyncio.create_task(self._run_refresh_window())

    async def _cancel_refresh_window(self) -> None:
        # cancel exactly as EcoFlowBleStation stops its maintainer, so exactly one loop and one live card survive
        if self._refresh_task is not None:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            self._refresh_task = None

    async def _remembered_message_id(self) -> int | None:
        async with self.uow_factory() as uow:
            posted = await uow.posted_messages.list_by_kind(TRANSIT_CARD_KIND)
        return posted[-1].message_id if posted else None
