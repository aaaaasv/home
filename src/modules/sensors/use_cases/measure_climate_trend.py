from datetime import date, timedelta

from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.sensors.domain import ClimateTrend, average_of

# a day the sensors barely spoke on averages badly, and one whose battery died at noon averages worse
LEAST_READINGS_FOR_A_DAY = 12
WEEK = 7


class MeasureClimateTrendUseCase(BaseUseCase):
    """
    Whether the flat is warmer or drier than it was yesterday and than it was over the past week.

    the comparison is what makes an indoor number worth reading at all. «24°» says nothing — a flat is always
    about that — while «на два градуси холодніше, ніж тиждень тому» is the first sign that the season turned,
    or that a window has been open since morning.

    folded days are compared rather than raw readings, so the answer is the same quantity whatever hour
    anybody asks at. today counts as far as it has got, which is what «за добу» means to a person reading it
    in the evening.
    """

    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar):
        super().__init__(uow)
        self.household_calendar = household_calendar

    async def __call__(self, sensors: set[str]) -> ClimateTrend:
        today = self.household_calendar.today()
        async with self.uow as uow:
            by_day: dict[date, list] = {}
            for sensor in sensors:
                for day in await uow.sensor_days.list_between(sensor, today - timedelta(days=WEEK), today):
                    if day.reading_count >= LEAST_READINGS_FOR_A_DAY:
                        by_day.setdefault(day.day, []).append(day)

        now = _across_rooms(by_day.get(today, []))
        yesterday = _across_rooms(by_day.get(today - timedelta(days=1), []))
        week = _across_rooms([row for day, rows in by_day.items() if day < today for row in rows])

        return ClimateTrend(
            temperature_change_since_yesterday=_difference(now.temperature, yesterday.temperature),
            temperature_change_since_last_week=_difference(now.temperature, week.temperature),
            humidity_change_since_yesterday=_difference(now.humidity, yesterday.humidity),
            humidity_change_since_last_week=_difference(now.humidity, week.humidity),
        )


class _Averages:
    def __init__(self, temperature: float | None, humidity: float | None):
        self.temperature = temperature
        self.humidity = humidity


def _across_rooms(days: list) -> _Averages:
    return _Averages(
        temperature=average_of(day.average_temperature_celsius for day in days),
        humidity=average_of(day.average_humidity_percent for day in days),
    )


def _difference(newer: float | None, older: float | None) -> float | None:
    return None if newer is None or older is None else newer - older
