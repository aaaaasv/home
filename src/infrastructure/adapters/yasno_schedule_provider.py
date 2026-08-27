"""Yasno planned-outage schedule for the Kyiv-city group the family lives under.

The public endpoint returns one object per group ("1.1" … "60.1"), each with a `today` and `tomorrow` block
(`slots`, `date`, `status`) and a per-group `updatedOn`. A slot is `{start, end, type}` where start/end are
minutes from midnight in the group's local day and `type == "Definite"` means the light will be off; other slot
types (e.g. "NotPlanned") are normal power and are dropped. Confirmed live 2026-08-11 against the real endpoint;
the slot schema matches denysdovhan/ha-yasno-outages (`api/models.py`).
"""

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import aiohttp

from src.modules.power.domain import OutageInterval, OutageOutlook, OutageSchedule, OutageScheduleStatus

logger = logging.getLogger(__name__)

PLANNED_OUTAGES_URL = (
    "https://app.yasno.ua/api/blackout-service/public/shutdowns/regions/{region_id}/dsos/{dso_id}/planned-outages"
)
REQUEST_TIMEOUT_SECONDS = 15
# kyiv city / дтек київські — the ids behind the endpoint the family's group belongs to
KYIV_CITY_REGION_ID = 25
KYIV_CITY_DSO_ID = 902
# only this slot type means the power is actually off; the api also emits normal-power stretches
DEFINITE_OFF_SLOT_TYPE = "Definite"
TODAY_KEY = "today"
TOMORROW_KEY = "tomorrow"


class YasnoScheduleProvider:
    """Fetches the planned-outage schedule for one Kyiv-city group — returns None when it cannot be trusted"""

    def __init__(
        self,
        group: str,
        timezone_name: str,
        region_id: int = KYIV_CITY_REGION_ID,
        dso_id: int = KYIV_CITY_DSO_ID,
    ) -> None:
        self.group = group
        self.timezone = ZoneInfo(timezone_name)
        self.region_id = region_id
        self.dso_id = dso_id

    async def fetch(self) -> OutageOutlook | None:
        payload = await self._fetch_payload()
        if payload is None:
            return None
        return parse_outage_outlook(payload, self.group)

    async def fetch_today(self) -> OutageSchedule | None:
        payload = await self._fetch_payload()
        if payload is None:
            return None
        return parse_outage_schedule(payload, self.group, TODAY_KEY)

    async def _fetch_payload(self) -> dict | None:
        url = PLANNED_OUTAGES_URL.format(region_id=self.region_id, dso_id=self.dso_id)
        try:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers={"accept": "application/json"}) as response:
                    response.raise_for_status()
                    return await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            logger.warning("Yasno schedule fetch failed: %r", error)
            return None


def parse_outage_outlook(payload: dict, group: str) -> OutageOutlook | None:
    today = parse_outage_schedule(payload, group, TODAY_KEY)
    if today is None:
        return None
    return OutageOutlook(today=today, tomorrow=parse_outage_schedule(payload, group, TOMORROW_KEY))


def parse_outage_schedule(payload: dict, group: str, day_key: str) -> OutageSchedule | None:
    group_data = payload.get(group)
    if not isinstance(group_data, dict):
        logger.warning("Yasno payload has no group %r", group)
        return None

    day_data = group_data.get(day_key)
    if not isinstance(day_data, dict) or "date" not in day_data:
        return None

    return OutageSchedule(
        day=datetime.fromisoformat(day_data["date"]).date(),
        status=OutageScheduleStatus(day_data.get("status", OutageScheduleStatus.UNKNOWN)),
        off_intervals=_parse_off_intervals(day_data.get("slots") or []),
        updated_on=_parse_updated_on(group_data.get("updatedOn")),
    )


def _parse_off_intervals(slots: list[dict]) -> tuple[OutageInterval, ...]:
    off_intervals = []
    for slot in slots:
        if slot.get("type") != DEFINITE_OFF_SLOT_TYPE:
            continue
        start = slot.get("start")
        end = slot.get("end")
        if start is None or end is None:
            continue
        off_intervals.append(OutageInterval(start_minute=int(start), end_minute=int(end)))
    off_intervals.sort(key=lambda interval: interval.start_minute)
    return _merge_adjacent(off_intervals)


def _merge_adjacent(intervals: list[OutageInterval]) -> tuple[OutageInterval, ...]:
    # the api splits a long outage into hourly slots — fuse touching ones so the card shows "16:00–19:30", not three
    merged: list[OutageInterval] = []
    for interval in intervals:
        if merged and interval.start_minute <= merged[-1].end_minute:
            previous = merged[-1]
            merged[-1] = OutageInterval(previous.start_minute, max(previous.end_minute, interval.end_minute))
        else:
            merged.append(interval)
    return tuple(merged)


def _parse_updated_on(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
