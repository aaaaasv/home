"""Turning what the map says into one card per tracked object in the owner's private chat.

Two callers, on purpose. The **socket** calls this the moment anything moves, which is the whole point: at
ballistic speed every second of our own delay is two thirds of a kilometre. The **slow job** calls the same
thing on a clock, because a card going stale is a passage of time rather than an event — nothing arrives to
say "that drone is gone", so somebody has to look.
"""
import logging
from collections.abc import Callable

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from src.bot.handlers.air_threats.formatting import render_gone, render_threat
from src.common.config import Settings
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.air_threats.commands import TrackAirThreatsCommand
from src.modules.air_threats.domain import ApproachingThreat
from src.modules.air_threats.services.air_threat_source import AirThreatSource
from src.modules.air_threats.use_cases.record_air_threat_message import RecordAirThreatMessageUseCase
from src.modules.air_threats.use_cases.track_air_threats import TrackAirThreatsUseCase

logger = logging.getLogger(__name__)


class AirThreatWatcher:
    """
    One card per tracked object, posted once and edited as it moves.

    a new track pings, because that is the whole point — something is coming. every later change is a silent
    edit of the same card: a track updates its position every few seconds, and a notification per update would
    teach the person to swipe the whole chat away, which is the one outcome that makes this worse than nothing.
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
                overhead_kilometres=self.settings.AIR_THREATS_OVERHEAD_KILOMETRES,
                warning_minutes=self.settings.AIR_THREATS_WARNING_MINUTES,
                approach_degrees=self.settings.AIR_THREATS_APPROACH_DEGREES,
                speeds_by_kind=self.settings.threat_speeds,
                default_speed=self.settings.AIR_THREATS_DEFAULT_SPEED,
            )
        )
        if changes is None:
            return

        # the new ones first and without waiting on anything: an edit can be late, an arrival cannot
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
        posted = await self.bot.send_message(chat_id=self.chat_id, text=text, disable_notification=False)
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
