import asyncio
import logging
from datetime import datetime
from typing import Protocol

import aiohttp

from src.common.time import current_time

logger = logging.getLogger(__name__)

STATUSES_URL = "https://vadimklimenko.com/map/statuses.json"
REQUEST_TIMEOUT_SECONDS = 15
CACHE_TIME_TO_LIVE_SECONDS = 30
# the endpoint 403s without a browser-like agent
USER_AGENT = "Mozilla/5.0 (X11; Linux aarch64) home-bot/1.0"


class AirRaidAlertSource(Protocol):
    """Whether the air-raid alert is active for the city — None when the status cannot be read"""

    async def is_alert_active(self) -> bool | None:
        ...


class AlarmMapAirRaidAlertSource:
    """Reads the city's air-raid flag from vadimklimenko's map — None when the status cannot be read"""

    def __init__(self, city_name: str = "м. Київ"):
        self.city_name = city_name
        self._cached_active: bool | None = None
        self._cached_at: datetime | None = None

    async def is_alert_active(self) -> bool | None:
        now = current_time()
        if self._cached_at is not None and (now - self._cached_at).total_seconds() < CACHE_TIME_TO_LIVE_SECONDS:
            return self._cached_active

        self._cached_active = parse_alert_active(await self._fetch_payload(), self.city_name)
        self._cached_at = now
        return self._cached_active

    async def _fetch_payload(self) -> dict | None:
        try:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(STATUSES_URL, headers={"User-Agent": USER_AGENT}) as response:
                    response.raise_for_status()
                    # the host serves the json as text/plain, so bypass the content-type guard
                    return await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            logger.warning("Air-raid status fetch failed: %r", error)
            return None


def parse_alert_active(payload: dict | None, city_name: str) -> bool | None:
    if not isinstance(payload, dict):
        return None
    states = payload.get("states")
    if not isinstance(states, dict):
        return None
    city = states.get(city_name)
    if not isinstance(city, dict) or "enabled" not in city:
        return None
    return bool(city["enabled"])
