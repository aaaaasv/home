"""Reading the alert level once per tick, and handing that one reading to everything that answers it."""
import logging
from collections.abc import Callable

from src.bot.handlers.air_alert.announcement import AlertAnnouncement
from src.bot.handlers.air_alert.light import AlertLight
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.air_alert.services.air_alert_source import AirAlertSource
from src.modules.air_alert.use_cases.follow_air_alert import FollowAirAlertUseCase

logger = logging.getLogger(__name__)


class AirAlertWatcher:
    """
    What the house does when the city goes red: the strip on the switchboard, and the card in the group.

    **the level may be read only once per tick**, which is why both halves hang off one object. the use case
    behind the reading writes what it saw to the database, so whoever reads second is told that nothing
    changed and does nothing at all. two copies of the strip's half is exactly the bug that left it burning
    for two hours on the night of 13/14.10.

    the socket drives this, and the clock behind it covers the one failure the socket cannot report about
    itself: a connection that is open, subscribed and silently dead.
    """

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        source: AirAlertSource,
        household_calendar: HouseholdCalendar,
        light: AlertLight | None = None,
        announcement: AlertAnnouncement | None = None,
    ):
        self.uow_factory = uow_factory
        self.source = source
        self.household_calendar = household_calendar
        self.light = light
        self.announcement = announcement

    async def __call__(self) -> None:
        transition, alert = await FollowAirAlertUseCase(
            uow=self.uow_factory(), source=self.source, household_calendar=self.household_calendar
        )()

        # the light goes first, and what it answers decides whether the card offers to put it out
        strip_is_up = await self.light.handle(transition, alert) if self.light is not None else False
        if self.announcement is not None:
            await self.announcement.handle(transition, alert, strip_is_up=strip_is_up)
