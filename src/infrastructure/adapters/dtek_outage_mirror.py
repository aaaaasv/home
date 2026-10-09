"""The grid operator's own daily table, which stays published when Yasno's feed goes empty.

During emergency shutdowns Yasno answers `status: EmergencyShutdowns` with no hours at all — verified live on
9 october 2026 for all sixty Kyiv groups, both days. DTEK keeps publishing its table regardless, and that
is the one the family sees in the city's own app. Its site sits behind an Imperva challenge that refuses
headless browsers, so this reads a mirror that polls DTEK every few minutes and commits the normalised
result as JSON.

The mirror's `origin` field is the load-bearing one: `fact` is the day's real table, `preset` is the standing
weekly grid, and only the former says anything about today. The weekly grid is dropped here rather than
rendered, because an hour nobody promised reads exactly like an hour somebody did.
"""

import asyncio
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import aiohttp

from src.modules.power.domain import OutageInterval

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 20
# the day's real table; the mirror also carries the standing weekly grid under "preset"
DAILY_TABLE_ORIGIN = "fact"
OFF_INTERVAL_KIND = "off"


class DtekOutageMirror:
    """Reads one group's hours out of the mirrored operator table — None whenever they cannot be trusted."""

    def __init__(self, url: str, group: str, timezone_name: str, stale_after: timedelta):
        self.url = url
        self.group = group
        self.timezone = ZoneInfo(timezone_name)
        self.stale_after = stale_after

    async def fetch_intervals(self, day: date) -> tuple[OutageInterval, ...] | None:
        payload = await self._fetch_payload()
        if payload is None:
            return None
        return parse_group_intervals(payload, self.group, day, self.timezone, self.stale_after)

    async def _fetch_payload(self) -> dict | None:
        try:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.url, headers={"accept": "application/json"}) as response:
                    response.raise_for_status()
                    return await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as error:
            logger.warning("DTEK mirror fetch failed: %r", error)
            return None


def parse_group_intervals(
    payload: dict,
    group: str,
    day: date,
    timezone: ZoneInfo,
    stale_after: timedelta,
) -> tuple[OutageInterval, ...] | None:
    """One group's off-hours for one day, or None when the mirror is stale, broken or silent about that day."""
    if not _is_fresh(payload, timezone, stale_after):
        return None

    schedules = payload.get("schedules")
    if not isinstance(schedules, dict):
        logger.warning("DTEK mirror holds no schedules")
        return None
    group_data = schedules.get(group)
    if not isinstance(group_data, dict):
        logger.warning("DTEK mirror has no group %r", group)
        return None

    intervals = []
    for interval in group_data.get("intervals") or []:
        if interval.get("origin") != DAILY_TABLE_ORIGIN or interval.get("kind") != OFF_INTERVAL_KIND:
            continue
        bounds = _parse_bounds(interval, day, timezone)
        if bounds is not None:
            intervals.append(bounds)
    intervals.sort(key=lambda interval: interval.start_minute)
    return tuple(intervals)


def _is_fresh(payload: dict, timezone: ZoneInfo, stale_after: timedelta) -> bool:
    """
    A frozen mirror answers 200 with yesterday's hours, so age is the only thing that catches it.

    the table is published once overnight, so it is hours old by design — the window has to be a day-ish
    rather than minutes, and `status.ok` carries the mirror's own verdict on its last poll.
    """
    status = payload.get("status")
    if isinstance(status, dict) and status.get("ok") is False:
        logger.warning("DTEK mirror reports its own last poll failed: %s", status.get("code"))
        return False

    updated_at = _parse_moment(payload.get("updatedAt"))
    if updated_at is None:
        logger.warning("DTEK mirror carries no update time")
        return False
    age = datetime.now(timezone) - updated_at
    if age > stale_after:
        logger.warning("DTEK mirror is stale — last updated %s", updated_at)
        return False
    return True


def _parse_bounds(interval: dict, day: date, timezone: ZoneInfo) -> OutageInterval | None:
    start = _parse_moment(interval.get("start"))
    end = _parse_moment(interval.get("end"))
    if start is None or end is None:
        return None
    start = start.astimezone(timezone)
    end = end.astimezone(timezone)
    if start.date() != day:
        return None
    # an interval running to midnight lands on the next date; 1440 is how the domain spells end-of-day
    end_minute = 24 * 60 if end.date() > day else end.hour * 60 + end.minute
    return OutageInterval(start_minute=start.hour * 60 + start.minute, end_minute=end_minute)


def _parse_moment(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
