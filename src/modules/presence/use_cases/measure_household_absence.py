from datetime import timedelta

from src.common.household_calendar import HouseholdCalendar
from src.common.time import as_utc
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.presence.domain import OUTCOMES_THAT_ARE_NOT_AN_ARRIVAL, HouseholdAbsence
from src.modules.presence.use_cases.record_presence_event import JOINED

# far enough back that a weekend away is still measurable, short enough that the replay stays a handful of rows
HORIZON = timedelta(days=2)


class MeasureHouseholdAbsenceUseCase(BaseUseCase):
    """
    Replays the log to find the moment the flat last stood empty, and for how long it has.

    **Call this before writing the join being judged**, so the replay ends with the arriving phone still away.

    the per-address version of this question was wrong, and the evening of 2026-09-26 showed exactly how. a
    phone wears a different private address on each SSID and this flat runs two, so at 22:41 one address left
    and another arrived three seconds later — the same phone, walking from one radio to the other. measured
    per address the second one had been gone for hours; measured per household nobody had gone anywhere.

    a phone arriving within the together window does not count as having occupied the flat before we got
    here: two people walk in seconds apart, and the second must not find the first already living there.
    """

    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar, together: timedelta):
        super().__init__(uow)
        self.household_calendar = household_calendar
        self.together = together

    async def __call__(self) -> HouseholdAbsence:
        now = self.household_calendar.now()
        window_start = now - HORIZON

        async with self.uow as uow:
            present = set()
            for mac in await uow.presence_events.list_macs():
                opening = await uow.presence_events.retrieve_last_event_before(mac, window_start)
                if opening is not None and opening.event == JOINED:
                    present.add(mac)

            empty_since = None
            for event in await uow.presence_events.list_since(window_start):
                at = as_utc(event.at)
                if event.event == JOINED:
                    if now - at <= self.together and event.outcome not in OUTCOMES_THAT_ARE_NOT_AN_ARRIVAL:
                        continue
                    present.add(event.mac)
                    empty_since = None
                    continue
                present.discard(event.mac)
                if not present and empty_since is None:
                    empty_since = at

        if present:
            return HouseholdAbsence(empty_for=None, somebody_stayed=True)
        if empty_since is None:
            # the log never saw the flat empty, so there is nothing to measure and being unsure means staying dark
            return HouseholdAbsence(empty_for=None, somebody_stayed=False)
        return HouseholdAbsence(empty_for=now - empty_since, somebody_stayed=False)
