from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.power.domain import DeclaredSupply, GridState


class DeclareSupplyUseCase(BaseUseCase):
    """
    Writes down what is feeding the pi's socket, and takes back the announcement that assumed the other thing.

    «ні, це Delta 2» is an answer to one particular message, so the row to retract is named by that message's
    own button rather than looked up here. guessing at «the latest row» would be a trap: tapped on a card
    from last week it would delete a true «світло є» and merge two outages into one in the journal every
    «скільько годин без світла» is counted from.

    the row is deleted rather than marked, because the journal is a log of transitions and its own docstring
    makes the length of an outage the gap between two rows. a retracted announcement leaves no transition
    behind it — the flat never came off the battery — and the next real one measures the whole outage.
    """

    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar):
        super().__init__(uow)
        self.household_calendar = household_calendar

    async def __call__(self, supply: DeclaredSupply, retract_grid_event_id: int | None = None) -> bool:
        """Answers whether a recorded announcement was taken back, which is what the reply has to say."""
        async with self.uow as uow:
            await uow.supply_declaration.save(supply=supply.value, declared_at=self.household_calendar.now())
            if retract_grid_event_id is None:
                return False

            # a stale button must not cut a hole in the middle of the journal: only the newest row may go,
            # and only while it is still the "the light is back" it was when the card was drawn
            latest = await uow.grid_events.retrieve_latest()
            if latest is None or latest.id != retract_grid_event_id or latest.state != GridState.ON_GRID.value:
                return False
            await uow.grid_events.delete(retract_grid_event_id)
        return True
