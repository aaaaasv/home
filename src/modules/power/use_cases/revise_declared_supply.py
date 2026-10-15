from datetime import timedelta

from src.common.household_calendar import HouseholdCalendar
from src.common.time import as_utc
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.power.domain import DeclaredSupply, UpsState

# the mark is sometimes tapped before the plug is moved, and for those few minutes the hat is still
# reading the dead socket it is about to leave
DECLARATION_GRACE = timedelta(minutes=10)


class ReviseDeclaredSupplyUseCase(BaseUseCase):
    """
    What is feeding the pi's socket, after checking the one thing the family's word cannot survive.

    a station feeding the pi gives it mains voltage, always. so a hat reporting **no** mains while the
    station is declared to feed it is a contradiction the hat wins: either the changeover was thrown back
    to the city, or the station was switched off, and in both cases the socket is a wall socket again.

    this is the question «як система дізнається, що я перемкнувся назад» answered without a button. on
    15.10.2026 the flat went onto the station for ten minutes mid-outage, was switched back, and nothing
    told the bot — the mark would have stood until the evening and swallowed the «світло є» that the
    whole house waits for.

    the grace period is there because the mark and the plug do not move in the same second.
    """

    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar, grace: timedelta = DECLARATION_GRACE):
        super().__init__(uow)
        self.household_calendar = household_calendar
        self.grace = grace

    async def __call__(self, ups: UpsState | None) -> DeclaredSupply:
        async with self.uow as uow:
            declared = await uow.supply_declaration.retrieve_current()
            if declared is None:
                return DeclaredSupply.GRID

            supply = DeclaredSupply(declared.supply)
            # an unreadable hat contradicts nothing, and mains is what the declaration itself predicts
            if supply is not DeclaredSupply.STATION or ups is None or ups.mains_present:
                return supply

            now = self.household_calendar.now()
            if now - as_utc(declared.declared_at) < self.grace:
                return supply

            await uow.supply_declaration.save(supply=DeclaredSupply.GRID.value, declared_at=now)
        return DeclaredSupply.GRID
