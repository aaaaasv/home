from datetime import datetime, timedelta

from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork

LEFT = "left"
JOINED = "joined"
# a phone that has been quiet this long is not coming back from a hop between bands
RETENTION_DAYS = 30


class RecordPresenceEventUseCase(BaseUseCase):
    """
    Writes down one join or departure, and answers how long the phone had been gone.

    on disk rather than in memory for two reasons that arrived on the same evening. measuring an absence
    across a restart is the first — a bot that forgets the departure cannot recognise the return, and the
    deploy that shipped the welcome light did exactly that an hour before anyone came home. the second is
    being able to look back and say whether the light ever came on by itself, which needs the refusals
    written down as well as the one success.
    """

    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar):
        super().__init__(uow)
        self.household_calendar = household_calendar

    async def __call__(self, mac: str, event: str, rssi: int | None) -> timedelta | None:
        """Records the event; for a join, returns how long the phone had been away, or None if unknown."""
        moment = self.household_calendar.now()
        async with self.uow as uow:
            away: timedelta | None = None
            if event == JOINED:
                departure = await uow.presence_events.retrieve_last_departure(mac)
                if departure is not None:
                    away = moment - _as_utc(departure.at)

            await uow.presence_events.create({"mac": mac, "event": event, "rssi": rssi, "at": moment})
            await uow.presence_events.delete_before(moment - timedelta(days=RETENTION_DAYS))
            return away


class RecordArrivalOutcomeUseCase(BaseUseCase):
    """Marks the join that was just written with what the welcome light decided, so the reason survives."""

    async def __call__(self, mac: str, outcome: str) -> None:
        async with self.uow as uow:
            recent = await uow.presence_events.retrieve_last_join(mac)
            if recent is not None:
                recent.outcome = outcome


def _as_utc(moment: datetime) -> datetime:
    """SQLite keeps no offset, and the column type re-attaches it — but a fresh row may arrive naive."""
    from datetime import timezone

    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
