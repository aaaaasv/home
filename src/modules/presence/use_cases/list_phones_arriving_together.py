from datetime import timedelta

from src.common.household_calendar import HouseholdCalendar
from src.common.time import as_utc
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.presence.domain import OUTCOMES_THAT_ARE_NOT_AN_ARRIVAL
from src.modules.presence.use_cases.record_presence_event import LEFT


class ListPhonesArrivingTogetherUseCase(BaseUseCase):
    """
    Of the other phones the router shows on the wi-fi, which are walking in beside this one.

    two people come home together far more often than one comes home alone, and the router sees both radios
    within a second or two. without this every such arrival refused itself — each phone read the other as
    somebody already at home, so the flat they both walked into stayed dark.

    a phone is arriving rather than resident when the log has it away while the router already has it back —
    its own join has simply not been handled yet — or when its last join is recent and was a real arrival. a
    join that was only a hop between bands proves nothing, so it leaves its owner counted as home.
    """

    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar, together: timedelta):
        super().__init__(uow)
        self.household_calendar = household_calendar
        self.together = together

    async def __call__(self, macs: set[str]) -> set[str]:
        moment = self.household_calendar.now()
        arriving = set()
        async with self.uow as uow:
            for mac in macs:
                latest = await uow.presence_events.retrieve_last_event(mac)
                if latest is None:
                    # never seen moving, so it has been sitting at home for as long as anybody remembers
                    continue
                if latest.event == LEFT:
                    arriving.add(mac)
                    continue
                recent = moment - as_utc(latest.at) <= self.together
                if recent and latest.outcome not in OUTCOMES_THAT_ARE_NOT_AN_ARRIVAL:
                    arriving.add(mac)
        return arriving
