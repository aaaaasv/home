from datetime import date, time

from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.domain import CareDigest

SATURDAY = 5


class DeliverDailyCareDigestUseCase(BaseUseCase):
    """
    Returns today's digest only if it is worth sending right now, so a periodic caller sends it exactly once a day.

    a plain daily cron loses the digest whenever the pi is down at that minute. this instead answers "is it past
    the digest time, have we not sent today, and is anything due?" — so the first check after the pi comes back
    delivers the reminder that a fixed-time cron would have silently dropped.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        household_calendar: HouseholdCalendar,
        digest_time: time,
        weekend_digest_time: time | None = None,
    ):
        super().__init__(uow)
        self.household_calendar = household_calendar
        self.digest_time = digest_time
        # nobody wants to be told to water anything at nine on a saturday
        self.weekend_digest_time = weekend_digest_time or digest_time

    def _digest_time_for(self, day: date) -> time:
        return self.weekend_digest_time if day.weekday() >= SATURDAY else self.digest_time

    async def __call__(self) -> CareDigest | None:
        today = self.household_calendar.today()
        if self.household_calendar.local_time(self.household_calendar.now()) < self._digest_time_for(today):
            return None

        async with self.uow as uow:
            if await uow.care_digest_deliveries.retrieve_last_sent_date() == today:
                return None
            due_schedules = await uow.care_schedules.list_due_with_plants(today)
            photo_file_ids = await uow.plant_photos.latest_file_ids([plant.id for _, plant in due_schedules])

        digest = CareDigest.from_due_schedules(today, due_schedules, photo_file_ids)
        return digest if digest.tasks else None
