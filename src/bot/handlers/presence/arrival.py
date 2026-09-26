"""Meeting whoever walks in: the strip comes up when a family phone joins the Wi-Fi after a real absence.

The timing is the whole point. A phone associates from the stairwell, several seconds before the door opens,
so the light is already up when the person steps into the hallway. Nothing that watches the inside of the
flat can do that — a motion sensor only sees you once you are already standing in the dark.

The price of being early is being wrong sometimes, and the router's own log shows exactly how wrong:

    16:12:10  left
    16:12:13  joined
    16:12:16  left

Six seconds, nobody walking anywhere. That is why an arrival is not «з'явився» but «не було достатньо довго»,
and why the threshold is counted in tens of minutes rather than in seconds.
"""
import json
import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from src.common.config import Settings
from src.common.daylight import is_dark
from src.common.household_calendar import HouseholdCalendar
from src.modules.lighting.services.panel_light import PanelLight
from src.modules.presence.services.presence_source import PresenceSource

logger = logging.getLogger(__name__)

JOINED = "joined"
LEFT = "left"


class ArrivalLightWatcher:
    """
    One rule with four refusals, and the refusals are what make it safe to leave switched on.

    it never touches a light that is already on, never turns one on in daylight, never turns one on when
    somebody is already home, and never treats a phone that merely hopped between bands as an arrival.
    """

    def __init__(
        self,
        panel_light: PanelLight,
        presence_source: PresenceSource,
        settings: Settings,
        household_calendar: HouseholdCalendar,
    ):
        self.panel_light = panel_light
        self.presence_source = presence_source
        self.settings = settings
        self.household_calendar = household_calendar
        self._left_at: dict[str, datetime] = {}
        self._raised_at: datetime | None = None

    async def handle(self, payload: str) -> None:
        """One event from the router's log, already turned into json by the host service."""
        try:
            report = json.loads(payload)
            mac = str(report["mac"]).upper()
            event = report["event"]
        except (ValueError, KeyError, TypeError):
            return

        if mac not in self.settings.presence_phone_macs:
            return

        moment = self.household_calendar.now()
        if event == LEFT:
            self._left_at[mac] = moment
            return
        if event != JOINED:
            return

        await self._consider_arrival(mac, moment)

    async def _consider_arrival(self, mac: str, moment: datetime) -> None:
        left_at = self._left_at.pop(mac, None)
        if left_at is None:
            # never seen leaving, so there is no absence to measure. that happens after a restart, and
            # staying dark is the right way to be unsure
            return
        away = moment - left_at
        if away < timedelta(minutes=self.settings.ARRIVAL_AWAY_MINUTES):
            logger.debug("%s was only away %s — a hop, not an arrival", mac, away)
            return

        if not is_dark(moment, self.settings.PRESENCE_LATITUDE, self.settings.PRESENCE_LONGITUDE):
            return

        if await self._somebody_else_is_home(mac):
            return

        standing = await self.panel_light.read()
        if standing is None or standing.is_on:
            return

        await self.panel_light.set_brightness(self.settings.ARRIVAL_LIGHT_PERCENT)
        self._raised_at = moment
        logger.info("Arrival: %s back after %s, light raised", mac, away)

    async def _somebody_else_is_home(self, arriving_mac: str) -> bool:
        """The point is meeting someone who walks into an empty dark flat; a full one needs no meeting."""
        online = await self.presence_source.online_macs()
        if online is None:
            # the router did not answer. treating that as "nobody home" would turn the light on for nothing,
            # and treating it as "somebody home" only costs this one arrival — so be the quiet one
            return True
        return bool((online & self.settings.presence_phone_macs) - {arriving_mac})

    async def sweep(self) -> None:
        """Put the light back out once the welcome has outlived its purpose."""
        if self._raised_at is None:
            return
        if self.household_calendar.now() - self._raised_at < timedelta(minutes=self.settings.ARRIVAL_LIGHT_MINUTES):
            return

        standing = await self.panel_light.read()
        if standing is not None and abs(standing.brightness_percent - self.settings.ARRIVAL_LIGHT_PERCENT) > 1:
            # a hand has been on it since — leave it where that hand put it
            self._raised_at = None
            return

        await self.panel_light.set_brightness(0)
        self._raised_at = None
        logger.info("Arrival light back out")


def build_arrival_handler(watcher: ArrivalLightWatcher) -> Callable:
    """Hand the mqtt side one thing it can call, so it never learns what a light or a router is."""

    async def handle(payload: str) -> None:
        await watcher.handle(payload)

    return handle
