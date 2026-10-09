"""Yasno's picture, with the operator's own hours poured into the days Yasno left empty."""
import logging
from dataclasses import replace
from typing import Protocol

from src.modules.power.domain import OutageInterval, OutageOutlook, OutageSchedule
from src.modules.power.services.outage_schedule_provider import OutageScheduleProvider

logger = logging.getLogger(__name__)


class OutageIntervalSource(Protocol):
    """One day's off-hours straight from the grid operator — None whenever they cannot be trusted"""

    async def fetch_intervals(self, day) -> tuple[OutageInterval, ...] | None:
        ...


class FilledOutageScheduleProvider:
    """
    Keeps Yasno as the answer and falls back to the operator only where Yasno has nothing to say.

    the two sources disagree by policy, not by accident: during emergency shutdowns Yasno publishes the regime
    and drops the hours, while DTEK publishes the hours and says separately that they are not in force. the
    family asked for both — the regime banner and the hours underneath — and reads the hours as the plan they
    are, so the status is taken from Yasno untouched and only the empty interval list is filled.

    yasno stays primary wherever it has hours, because it is the source that moves intraday; the operator's
    table is written once overnight. and a day Yasno cannot be read at all yields nothing: a card built on
    the fallback alone would carry hours with no idea whether the schedule even applies.
    """

    def __init__(self, published: OutageScheduleProvider, operator_table: OutageIntervalSource):
        self.published = published
        self.operator_table = operator_table

    async def fetch(self) -> OutageOutlook | None:
        outlook = await self.published.fetch()
        if outlook is None:
            return None
        return OutageOutlook(
            today=await self._fill(outlook.today),
            tomorrow=await self._fill(outlook.tomorrow) if outlook.tomorrow is not None else None,
        )

    async def fetch_today(self) -> OutageSchedule | None:
        today = await self.published.fetch_today()
        if today is None:
            return None
        return await self._fill(today)

    async def _fill(self, schedule: OutageSchedule) -> OutageSchedule:
        if schedule.has_outages:
            return schedule
        intervals = await self.operator_table.fetch_intervals(schedule.day)
        if not intervals:
            return schedule
        logger.info("Filled %s from the operator table: %d interval(s)", schedule.day.isoformat(), len(intervals))
        return replace(schedule, off_intervals=intervals)
