"""Raising the strip when a red alert starts, and putting it back when it ends.

The rule that matters most here is the one about not touching a light somebody is already using. At three in
the morning the person may have switched it on themselves, or left it at a level they chose; overriding that
because a feed changed state is the behaviour that gets an automation disabled for good.
"""
import logging
from collections.abc import Callable

from src.common.config import Settings
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.air_alert.domain import AlertTransition
from src.modules.air_alert.services.air_alert_source import AirAlertSource
from src.modules.air_alert.use_cases.follow_air_alert import FollowAirAlertUseCase
from src.modules.lighting.services.panel_light import PanelLight

logger = logging.getLogger(__name__)


class AlertLightWatcher:
    """
    One decision, taken twice: bring the light up when a red alert begins, and put it out when it ends.

    it is driven by the socket rather than a clock, because the whole point is the seconds. the poll behind
    the source is only there for the case the socket is quietly dead.
    """

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        source: AirAlertSource,
        panel_light: PanelLight,
        settings: Settings,
        household_calendar: HouseholdCalendar,
    ):
        self.uow_factory = uow_factory
        self.source = source
        self.panel_light = panel_light
        self.settings = settings
        self.household_calendar = household_calendar
        # whether the light standing at the alert level is our doing; an alert that began before the bot
        # started is deliberately not claimed, so we never put out something we did not turn on
        self._raised_it = False

    async def __call__(self) -> None:
        transition, alert = await FollowAirAlertUseCase(
            uow=self.uow_factory(), source=self.source, household_calendar=self.household_calendar
        )()

        if transition == AlertTransition.RAISED:
            await self._raise(alert)
        elif transition == AlertTransition.CLEARED:
            await self._lower()

    async def _raise(self, alert) -> None:
        standing = await self.panel_light.read()
        if standing is None:
            logger.warning("Red alert, but the light service is not answering")
            return
        if standing.is_on:
            # somebody is already using it — their level, their business
            logger.info("Red alert: the light is already on at %.0f%%, leaving it", standing.brightness_percent)
            return

        await self.panel_light.set_brightness(self.settings.ALERT_LIGHT_PERCENT)
        self._raised_it = True
        logger.info(
            "Red alert (%s): light raised to %.0f%%",
            alert.reason if alert else "без причини",
            self.settings.ALERT_LIGHT_PERCENT,
        )

    async def _lower(self) -> None:
        if not self._raised_it:
            logger.info("All clear, but the light was not ours to put out")
            return

        standing = await self.panel_light.read()
        if standing is not None and abs(standing.brightness_percent - self.settings.ALERT_LIGHT_PERCENT) > 1:
            # it moved since we set it, so a hand has been on it — leave it where that hand put it
            logger.info("All clear, but the light was changed by hand; leaving it")
            self._raised_it = False
            return

        await self.panel_light.set_brightness(0)
        self._raised_it = False
        logger.info("All clear: light back out")
