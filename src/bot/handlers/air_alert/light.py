"""Raising the strip when a red alert starts, and putting it back after a fixed while.

**The light goes out on a clock, not on the all-clear.** It exists for the few minutes of putting shoes on and
getting out; after that it is just a light burning through an alert that may run for hours. Waiting for the
all-clear also tied it to the feed being right twice instead of once.

The rule that matters most here is the one about not touching a light somebody is already using. At three in
the morning the person may have switched it on themselves, or left it at a level they chose; overriding that
because a feed changed state is the behaviour that gets an automation disabled for good.
"""
import logging
from collections.abc import Callable
from datetime import timedelta

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
        # when we raised it, or None when the light standing there is not our doing; an alert that began
        # before the bot started is deliberately not claimed, so we never put out something we did not turn on
        self._raised_at = None

    async def __call__(self) -> None:
        transition, alert = await FollowAirAlertUseCase(
            uow=self.uow_factory(), source=self.source, household_calendar=self.household_calendar
        )()

        if transition == AlertTransition.RAISED:
            await self._raise(alert)
        await self._sweep()

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
        self._raised_at = self.household_calendar.now()
        logger.info(
            "Red alert (%s): light raised to %.0f%%",
            alert.reason if alert else "без причини",
            self.settings.ALERT_LIGHT_PERCENT,
        )

    async def _sweep(self) -> None:
        """Put it out once the minutes it was raised for have passed, whatever the alert is doing by then."""
        if self._raised_at is None:
            return
        if self.household_calendar.now() - self._raised_at < timedelta(minutes=self.settings.ALERT_LIGHT_MINUTES):
            return

        standing = await self.panel_light.read()
        if standing is not None and abs(standing.brightness_percent - self.settings.ALERT_LIGHT_PERCENT) > 1:
            # it moved since we set it, so a hand has been on it — leave it where that hand put it
            logger.info("The alert light was changed by hand; leaving it")
            self._raised_at = None
            return

        await self.panel_light.set_brightness(0)
        self._raised_at = None
        logger.info("Alert light back out after %d minutes", self.settings.ALERT_LIGHT_MINUTES)
