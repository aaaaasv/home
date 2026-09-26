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

Which phone counts as ours is asked of the router by name rather than read from a list of addresses, because
iOS rotates the private address it wears on this network — see `src.modules.presence.domain`.

**Every decision is written down, including every refusal.** Two reasons, and both turned up the same
evening. The absence has to be measurable across a restart — the deploy that shipped this feature wiped an
in-memory departure an hour before anybody came home, which would have meant a dark hallway and no
explanation for it. And the morning after, «чи не вмикалось воно саме, поки нас не було» has to be
answerable by a query rather than by trusting whoever chose the thresholds.
"""
import json
import logging
from collections.abc import Callable
from datetime import timedelta

from src.common.config import Settings
from src.common.daylight import is_dark
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.lighting.services.panel_light import PanelLight
from src.modules.presence.domain import (
    RAISED,
    REFUSED_DAYLIGHT,
    REFUSED_HOP,
    REFUSED_LIGHT_ON,
    REFUSED_NO_DEPARTURE,
    REFUSED_ROUTER_SILENT,
    REFUSED_SOMEBODY_HOME,
)
from src.modules.presence.services.family_phones import FamilyPhones
from src.modules.presence.use_cases.list_phones_arriving_together import ListPhonesArrivingTogetherUseCase
from src.modules.presence.use_cases.record_presence_event import (
    JOINED,
    LEFT,
    RecordArrivalOutcomeUseCase,
    RecordPresenceEventUseCase,
)

logger = logging.getLogger(__name__)


class ArrivalLightWatcher:
    """
    One rule with several refusals, and the refusals are what make it safe to leave switched on.

    it never touches a light that is already on, never turns one on in daylight, never turns one on when
    somebody is already home, and never treats a phone that merely hopped between bands as an arrival.
    """

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        panel_light: PanelLight,
        family_phones: FamilyPhones,
        settings: Settings,
        household_calendar: HouseholdCalendar,
    ):
        self.uow_factory = uow_factory
        self.panel_light = panel_light
        self.family_phones = family_phones
        self.settings = settings
        self.household_calendar = household_calendar
        self._raised_at = None

    async def handle(self, payload: str) -> None:
        """One event from the router's log, already turned into json by the host service."""
        try:
            report = json.loads(payload)
            mac = str(report["mac"]).upper()
            event = report["event"]
        except (ValueError, KeyError, TypeError):
            return

        if event not in (JOINED, LEFT) or not await self.family_phones.recognises(mac):
            # somebody else's device on the same wi-fi, or a router that cannot say — not ours to record
            return

        rssi = report.get("rssi")
        away = await RecordPresenceEventUseCase(uow=self.uow_factory(), household_calendar=self.household_calendar)(
            mac, event, int(rssi) if isinstance(rssi, (int, float)) else None
        )

        if event == JOINED:
            outcome = await self._consider_arrival(mac, away)
            await RecordArrivalOutcomeUseCase(uow=self.uow_factory())(mac, outcome)
            logger.info("Arrival check for %s: %s (away %s)", mac, outcome, away)

    async def _consider_arrival(self, mac: str, away: timedelta | None) -> str:
        if away is None:
            # never seen leaving, so there is no absence to measure — staying dark is how to be unsure
            return REFUSED_NO_DEPARTURE
        if away < timedelta(minutes=self.settings.ARRIVAL_AWAY_MINUTES):
            return REFUSED_HOP

        moment = self.household_calendar.now()
        if not is_dark(moment, self.settings.PRESENCE_LATITUDE, self.settings.PRESENCE_LONGITUDE):
            return REFUSED_DAYLIGHT

        roster = await self.family_phones.read_roster()
        if roster is None:
            # the router did not answer. treating that as "nobody home" would light an empty hallway, and
            # treating it as "somebody home" costs only this one arrival — so be the quiet one
            return REFUSED_ROUTER_SILENT
        others = roster.others_online(mac)
        arriving_together = await ListPhonesArrivingTogetherUseCase(
            uow=self.uow_factory(),
            household_calendar=self.household_calendar,
            together=timedelta(minutes=self.settings.ARRIVAL_TOGETHER_MINUTES),
        )(others)
        if others - arriving_together:
            return REFUSED_SOMEBODY_HOME

        standing = await self.panel_light.read()
        if standing is None or standing.is_on:
            return REFUSED_LIGHT_ON

        await self.panel_light.set_brightness(self.settings.ARRIVAL_LIGHT_PERCENT)
        self._raised_at = moment
        return RAISED

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
