from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from src.common.time import current_time


class HouseholdCalendar:
    """Owns every conversion between an instant and the household's calendar day"""

    def __init__(self, timezone: ZoneInfo):
        self.timezone = timezone

    def now(self) -> datetime:
        return current_time()

    def today(self) -> date:
        return self.local_date(self.now())

    def local_date(self, moment: datetime) -> date:
        return moment.astimezone(self.timezone).date()

    def local_time(self, moment: datetime) -> time:
        # naive on purpose: it is compared to the naive digest time from the settings
        return moment.astimezone(self.timezone).time()

    def next_due_on(self, performed_at: datetime, interval_days: int) -> date:
        return self.local_date(performed_at) + timedelta(days=interval_days)

    def next_due_on_after_date(self, performed_on: date, interval_days: int) -> date:
        return performed_on + timedelta(days=interval_days)
