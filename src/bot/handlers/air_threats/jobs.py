"""Polling the threat map and keeping one card per tracked object in the owner's private chat."""
import logging
from collections.abc import Callable

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.bot.handlers.air_threats.formatting import render_gone, render_threat
from src.bot.scheduling import SchedulerContext
from src.common.config import Settings
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.air_threats.commands import TrackAirThreatsCommand
from src.modules.air_threats.domain import ApproachingThreat
from src.modules.air_threats.services.air_threat_source import AirThreatSource
from src.modules.air_threats.use_cases.record_air_threat_message import RecordAirThreatMessageUseCase
from src.modules.air_threats.use_cases.track_air_threats import TrackAirThreatsUseCase

logger = logging.getLogger(__name__)


class AirThreatWatchJob:
    """
    One card per tracked object, posted once and edited as it moves.

    a new track pings, because that is the whole point — something is in the air near us. every later change
    is an edit of the same card and stays silent: a drone updates its position every few seconds, and a
    notification per update would train the person to swipe the whole chat away.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        uow_factory: Callable[[], UnitOfWork],
        source: AirThreatSource,
        settings: Settings,
        household_calendar: HouseholdCalendar,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.uow_factory = uow_factory
        self.source = source
        self.settings = settings
        self.household_calendar = household_calendar

    async def __call__(self) -> None:
        changes = await TrackAirThreatsUseCase(
            uow=self.uow_factory(),
            source=self.source,
            household_calendar=self.household_calendar,
            stale_after_seconds=self.settings.AIR_THREATS_STALE_SECONDS,
        )(
            TrackAirThreatsCommand(
                latitude=self.settings.AIR_THREATS_LATITUDE,
                longitude=self.settings.AIR_THREATS_LONGITUDE,
                near_kilometres=self.settings.AIR_THREATS_NEAR_KILOMETRES,
                approach_degrees=self.settings.AIR_THREATS_APPROACH_DEGREES,
                inbound_kinds=self.settings.inbound_threat_kinds,
            )
        )
        if changes is None:
            return

        for approaching in changes.appeared:
            await self._post(approaching)
        for approaching in changes.standing:
            await self._rewrite(approaching)
        for tracker_id in changes.gone:
            await self._close(tracker_id)

        if changes.appeared or changes.gone:
            logger.info(
                "Air threats: %s new, %s standing, %s gone",
                len(changes.appeared),
                len(changes.standing),
                len(changes.gone),
            )

    async def _post(self, approaching: ApproachingThreat) -> None:
        text = self._render(approaching)
        posted = await self.bot.send_message(
            chat_id=self.chat_id,
            text=text,
            # a track that just came into range is exactly the thing worth looking up from the phone for
            disable_notification=False,
        )
        await self._remember(approaching.threat.tracker_id, posted.message_id, text)

    async def _rewrite(self, approaching: ApproachingThreat) -> None:
        text = self._render(approaching)
        async with self.uow_factory() as uow:
            notice = await uow.air_threat_notices.retrieve_by_tracker(approaching.threat.tracker_id)
            message_id = notice.message_id if notice else None
            unchanged = notice is not None and notice.rendered_text == text
        if message_id is None or unchanged:
            return

        try:
            await self.bot.edit_message_text(chat_id=self.chat_id, message_id=message_id, text=text)
        except TelegramBadRequest:
            # older than 48 hours, or deleted by hand — either way the card is not ours to keep updating
            return
        await self._remember(approaching.threat.tracker_id, message_id, text)

    async def _close(self, tracker_id: str) -> None:
        async with self.uow_factory() as uow:
            notice = await uow.air_threat_notices.retrieve_by_tracker(tracker_id)
            message_id = notice.message_id if notice else None
            previous_text = notice.rendered_text if notice else None
        if message_id is None or previous_text is None:
            return

        try:
            await self.bot.edit_message_text(
                chat_id=self.chat_id, message_id=message_id, text=render_gone(previous_text)
            )
        except TelegramBadRequest:
            return

    def _render(self, approaching: ApproachingThreat) -> str:
        return render_threat(approaching, self.settings.AIR_THREATS_LATITUDE, self.settings.AIR_THREATS_LONGITUDE)

    async def _remember(self, tracker_id: str, message_id: int, text: str) -> None:
        await RecordAirThreatMessageUseCase(uow=self.uow_factory())(tracker_id, self.chat_id, message_id, text)


def register_jobs(scheduler: AsyncIOScheduler, context: SchedulerContext) -> None:
    """Nothing to watch without a map, a place and somebody to tell — any one missing and the module stays off."""
    settings = context.settings
    if not settings.AIR_THREATS_ENABLED or context.air_threat_source is None or not settings.AIR_THREATS_CHAT_ID:
        return

    watch_job = AirThreatWatchJob(
        bot=context.bot,
        chat_id=settings.AIR_THREATS_CHAT_ID,
        uow_factory=context.uow_factory,
        source=context.air_threat_source,
        settings=settings,
        household_calendar=context.household_calendar,
    )
    scheduler.add_job(
        watch_job.__call__,
        trigger=IntervalTrigger(seconds=settings.AIR_THREATS_POLL_SECONDS),
        id="air_threats",
        replace_existing=True,
    )
