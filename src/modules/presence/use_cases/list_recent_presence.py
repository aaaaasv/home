from datetime import timedelta

from src.common.household_calendar import HouseholdCalendar
from src.common.time import as_utc
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.presence.domain import PresenceLogEntry


class ListRecentPresenceUseCase(BaseUseCase):
    """
    The last few days of joins and departures, oldest first, each with what the welcome light decided.

    it answers «о котрій ми вчора прийшли» and «чому вночі горіло світло» from the log that was written down for
    exactly that. phones are numbered by their sorted address so the same phone keeps its number through one
    answer without the address itself ever leaving the module.
    """

    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar):
        super().__init__(uow)
        self.household_calendar = household_calendar

    async def __call__(self, days: int, limit: int) -> list[PresenceLogEntry]:
        since = self.household_calendar.now() - timedelta(days=days)
        async with self.uow as uow:
            addresses = sorted(await uow.presence_events.list_macs())
            phone_number_by_mac = {mac: number for number, mac in enumerate(addresses, 1)}
            events = await uow.presence_events.list_since(since)

        return [
            PresenceLogEntry(
                phone_number=phone_number_by_mac[event.mac],
                event=event.event,
                outcome=event.outcome,
                at=as_utc(event.at),
            )
            for event in events[-limit:]
        ]
