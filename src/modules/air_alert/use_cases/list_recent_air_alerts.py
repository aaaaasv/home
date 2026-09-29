from datetime import timedelta

from src.common.household_calendar import HouseholdCalendar
from src.common.time import as_utc
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.air_alert.domain import AlertJournalEntry, AlertLevel, AlertTransition


class ListRecentAirAlertsUseCase(BaseUseCase):
    """
    The last few days of alert level changes, oldest first — the journal that exists so a night can be rebuilt.

    it answers «коли вчора була тривога» and «чому вночі горіло світло» from what the feed reported rather than
    from what anyone remembers of a night spent half asleep.
    """

    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar):
        super().__init__(uow)
        self.household_calendar = household_calendar

    async def __call__(self, days: int, limit: int) -> list[AlertJournalEntry]:
        since = self.household_calendar.now() - timedelta(days=days)
        async with self.uow as uow:
            events = await uow.air_alert_events.list_since(since)

        return [
            AlertJournalEntry(
                level=AlertLevel(event.level),
                reason=event.reason,
                transition=AlertTransition(event.outcome or AlertTransition.UNCHANGED),
                source=event.source,
                at=as_utc(event.at),
            )
            for event in events[-limit:]
        ]
