from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.air_alert.domain import AirAlert, AlertLevel, AlertTransition
from src.modules.air_alert.services.air_alert_source import AirAlertSource


class FollowAirAlertUseCase(BaseUseCase):
    """
    Watches the alert level for one place and reports only the two moments that call for an action.

    the level is remembered in the database rather than in memory because a restart in the middle of an
    alert must not look like the alert beginning again: the light is already up, and raising it a second
    time would fight whatever the person did with it since.

    only **red** counts. a yellow drone warning runs for hours several nights a week, and a light that
    answers every one of them is a light that gets switched off for good — after which it is not there on
    the night it matters.
    """

    def __init__(self, uow: UnitOfWork, source: AirAlertSource, household_calendar: HouseholdCalendar):
        super().__init__(uow)
        self.source = source
        self.household_calendar = household_calendar

    async def __call__(self) -> tuple[AlertTransition, AirAlert | None]:
        alert = await self.source.read_current()
        if alert is None:
            # the feed is unreachable. an unknown level is not an all-clear, so nothing is decided and
            # nothing is written — whatever was raised stays raised until we actually hear otherwise
            return AlertTransition.UNCHANGED, None

        async with self.uow as uow:
            remembered = await uow.air_alert_state.retrieve()
            previous = AlertLevel(remembered.level) if remembered else AlertLevel.NONE
            await uow.air_alert_state.save(
                level=alert.level, reason=alert.reason, changed_at=self.household_calendar.now()
            )

        was_red = previous == AlertLevel.RED
        is_red = alert.level == AlertLevel.RED
        if is_red and not was_red:
            return AlertTransition.RAISED, alert
        if was_red and not is_red:
            return AlertTransition.CLEARED, alert
        return AlertTransition.UNCHANGED, alert
