from datetime import timedelta

from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.sensors.domain import ClimateTrend, average_of

DAY = timedelta(days=1)
WEEK = 7
# a day the sensors barely spoke on averages badly, and one whose battery died at noon averages worse
LEAST_READINGS_FOR_A_DAY = 12


class MeasureClimateTrendUseCase(BaseUseCase):
    """
    Whether the flat is warmer or drier than it was a day and a week ago.

    the comparison is what makes an indoor number worth reading at all. «24°» says nothing — a flat is always
    about that — while «на два градуси холодніше, ніж тиждень тому» is the first sign that the season turned,
    or that a window has been open since morning.

    **the windows are the same length on purpose.** comparing today-so-far against a whole yesterday looked
    obvious and was wrong: read at eight in the morning, today-so-far is the night, so the digest would have
    announced that the flat is colder than yesterday every single morning and taught everybody to skip the
    line. a rolling twenty-four hours covers a full cycle, so neither end is biased by the hour of asking.

    the week is taken from folded days rather than raw readings because raw ones are pruned after seven days,
    and a whole day is unbiased for the same reason a rolling day is.
    """

    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar):
        super().__init__(uow)
        self.household_calendar = household_calendar

    async def __call__(self, sensors: set[str]) -> ClimateTrend:
        now = self.household_calendar.now()
        today = self.household_calendar.today()

        async with self.uow as uow:
            recent = await uow.sensor_readings.average_between(sensors, now - DAY, now)
            previous = await uow.sensor_readings.average_between(sensors, now - 2 * DAY, now - DAY)

            week_days = []
            for sensor in sensors:
                for day in await uow.sensor_days.list_between(sensor, today - timedelta(days=WEEK), today - DAY):
                    if day.reading_count >= LEAST_READINGS_FOR_A_DAY:
                        week_days.append(day)

        week = (
            average_of(day.average_temperature_celsius for day in week_days),
            average_of(day.average_humidity_percent for day in week_days),
        )
        return ClimateTrend(
            temperature_change_since_yesterday=_difference(recent[0], previous[0]),
            temperature_change_since_last_week=_difference(recent[0], week[0]),
            humidity_change_since_yesterday=_difference(recent[1], previous[1]),
            humidity_change_since_last_week=_difference(recent[1], week[1]),
        )


def _difference(newer: float | None, older: float | None) -> float | None:
    return None if newer is None or older is None else newer - older
