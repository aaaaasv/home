import logging
from collections.abc import Callable
from datetime import datetime, tzinfo

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from src.bot.handlers.power.formatting import render_reserve_board
from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.bot.services.posted_message_tracker import RESERVE_BOARD_KIND, PostedMessageTracker
from src.infrastructure.db.uow import UnitOfWork
from src.modules.power.domain import GridState, Reserve
from src.modules.power.mains_monitor import classify_grid
from src.modules.power.reserve import ElapsedClock, build_reserve
from src.modules.power.services.ecoflow_station import EcoFlowStation
from src.modules.power.services.pi_ups import PiUps
from src.modules.power.services.router_link import RouterLink

logger = logging.getLogger(__name__)

# a bot may edit its own message for 48h; past that the board is reposted rather than left stale
UNEDITABLE_MESSAGE_ERRORS = ("message to edit not found", "message can't be edited", "message_id_invalid")


class ReserveBoard:
    """
    Every backup layer as one standing, self-editing message — the screen you open to ask how long this lasts.

    it never notifies. the two messages that wake the family are the mains pushes, and this is what they come
    here to read afterwards; a board that pinged on every edit would get the whole topic muted, and a muted
    topic takes those pushes down with it. `/eco` deliberately stays separate: it carries buttons, and controls
    cannot live on a long-lived self-editing card.

    the two clocks are held here rather than in the job, because they are what the board knows and the job is
    only its cadence — and because a card reposted after 48h has to keep counting from the same moment. they
    are two and not one on purpose: `build_reserve` explains why the city and the wall socket part company.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        power_topic: ForumTopicRegistry,
        uow_factory: Callable[[], UnitOfWork],
        ecoflow_station: EcoFlowStation,
        pi_ups: PiUps,
        router_link: RouterLink,
        timezone: tzinfo,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.power_topic = power_topic
        self.uow_factory = uow_factory
        self.ecoflow_station = ecoflow_station
        self.pi_ups = pi_ups
        self.router_link = router_link
        self.timezone = timezone
        self.tracker = PostedMessageTracker(bot=bot, uow_factory=uow_factory)
        self._on_battery_clock = ElapsedClock()
        self._socket_dead_clock = ElapsedClock()

    async def compose(self) -> Reserve:
        """Read all three layers and stamp the two clocks, so the caller only has to decide whether to draw it."""
        ups = await self.pi_ups.read_state()
        station = await self.ecoflow_station.read_state()
        router_alive = await self.router_link.is_alive()
        now = datetime.now(self.timezone)

        grid = classify_grid(ups, station)
        return build_reserve(
            grid=grid,
            station=station,
            ups=ups,
            router_alive=router_alive,
            on_battery_for=self._on_battery_clock.update(grid is GridState.ON_BATTERY, now),
            socket_dead_for=self._socket_dead_clock.update(ups is not None and not ups.mains_present, now),
        )

    async def post(self, reserve: Reserve | None = None) -> None:
        """On /reserve — move the board to the bottom of the topic, where the person is already looking."""
        reserve = reserve if reserve is not None else await self.compose()

        await self.tracker.clear(RESERVE_BOARD_KIND)
        message = await self.bot.send_message(
            chat_id=self.chat_id,
            message_thread_id=await self.power_topic.resolve(),
            text=render_reserve_board(reserve, datetime.now(self.timezone)),
            # a glance, not a call to action — deliver and refresh it without a notification
            disable_notification=True,
        )
        await self.tracker.remember(RESERVE_BOARD_KIND, message)
        logger.info("Posted the reserve board, grid %s", reserve.grid.value)

    async def refresh(self, reserve: Reserve | None = None) -> bool:
        """Rewrite the standing board in place; False when there is none yet, so the caller can publish the first."""
        message_id = await self._remembered_message_id()
        if message_id is None:
            return False

        reserve = reserve if reserve is not None else await self.compose()
        try:
            await self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=message_id,
                text=render_reserve_board(reserve, datetime.now(self.timezone)),
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

    async def _remembered_message_id(self) -> int | None:
        async with self.uow_factory() as uow:
            posted = await uow.posted_messages.list_by_kind(RESERVE_BOARD_KIND)
        return posted[-1].message_id if posted else None
