"""Raising the strip when a red alert starts, and letting the host put it back after a fixed while.

**The light goes out on a clock, not on the all-clear.** It exists for the few minutes of putting shoes on and
getting out; after that it is just a light burning through an alert that may run for hours. Waiting for the
all-clear also tied it to the feed being right twice instead of once.

**That clock is not kept here.** It used to be: the raise moment lived in this object and a sweep on the
alert poll put the strip out, so a deploy or a reboot mid-alert lost it and the strip burned till morning —
twice, and the second time somebody ended up on a wardrobe unplugging it. The raise now names its own
minutes and the host service holds the deadline on disk, which is the one place a restart cannot reach.
What is left here is bookkeeping for the card's button, and nothing the light depends on.

The rule that matters most here is the one about not touching a light somebody is already using. At three in
the morning the person may have switched it on themselves, or left it at a level they chose; overriding that
because a feed changed state is the behaviour that gets an automation disabled for good.
"""
import logging
from datetime import timedelta

from src.common.config import Settings
from src.common.household_calendar import HouseholdCalendar
from src.modules.air_alert.domain import AirAlert, AlertTransition
from src.modules.lighting.services.panel_light import PanelLight

logger = logging.getLogger(__name__)


class AlertLight:
    """
    One decision, taken twice: bring the light up when a red alert begins, and put it out a while later.

    it is driven by the socket rather than a clock, because the whole point is the seconds. the poll behind
    the source is only there for the case the socket is quietly dead.
    """

    def __init__(self, panel_light: PanelLight, settings: Settings, household_calendar: HouseholdCalendar):
        self.panel_light = panel_light
        self.settings = settings
        self.household_calendar = household_calendar
        # when we raised it, or None when the light standing there is not our doing; an alert that began
        # before the bot started is deliberately not claimed, so we never put out something we did not turn on
        self._raised_at = None

    async def handle(self, transition: AlertTransition, alert: AirAlert | None) -> bool:
        """Whether the strip is standing at the alert level by our hand — which is what the card's button needs."""
        if transition == AlertTransition.RAISED:
            await self._raise(alert)
        return self._is_ours()

    async def _raise(self, alert: AirAlert | None) -> None:
        standing = await self.panel_light.read()
        if standing is None:
            logger.warning("Red alert, but the light service is not answering")
            return
        if standing.is_on:
            # somebody is already using it — their level, their business
            logger.info("Red alert: the light is already on at %.0f%%, leaving it", standing.brightness_percent)
            return

        await self.panel_light.set_brightness(
            self.settings.ALERT_LIGHT_PERCENT, minutes=self.settings.ALERT_LIGHT_MINUTES
        )
        self._raised_at = self.household_calendar.now()
        logger.info(
            "Red alert (%s): light raised to %.0f%% for %d min",
            alert.reason if alert else "без причини",
            self.settings.ALERT_LIGHT_PERCENT,
            self.settings.ALERT_LIGHT_MINUTES,
        )

    def _is_ours(self) -> bool:
        """
        Whether the light we raised is still standing — which is all «Погасити стрічку» needs to know.

        it is a count of minutes and not a reading, for two reasons. the strip standing at the alert level
        tells nobody whose hand put it there — and the host publishes its state on its own poll, so a read
        taken in the same tick as the raise still says «off» and would drop the button off every card.
        once the minutes are up the host has taken the light down, so the claim lapses here at the same
        moment. a hand that moves the strip meanwhile takes the lease with it, which is the host's affair.
        """
        if self._raised_at is None:
            return False
        if self.household_calendar.now() - self._raised_at >= timedelta(minutes=self.settings.ALERT_LIGHT_MINUTES):
            self._raised_at = None
        return self._raised_at is not None
