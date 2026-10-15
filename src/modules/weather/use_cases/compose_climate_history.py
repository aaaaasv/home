from datetime import date, timedelta
from statistics import median

from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.weather.domain import ClimateDay, ClimateHistory

# a day the sensors barely spoke on averages badly, and one whose battery died at noon averages worse —
# the same bar the climate trend uses, for the same reason
LEAST_READINGS_FOR_A_DAY = 12


class ComposeClimateHistoryUseCase(BaseUseCase):
    """
    The month behind us as two daily series: the rooms, and the sky.

    **finished days only.** every row here is an average over a day, and today's is an average over however
    many hours have happened — at eight in the morning that is the night, which would put a false dip at the
    right edge of every chart drawn before noon.

    the flat speaks as the **median of its rooms** rather than one sensor. the shelf sensor was the obvious
    candidate and reads half a degree warm, because it stands where the cooking happens; the median of four
    rooms moves only when the flat moves, and one window left open cannot drag the line on its own.

    it reads the sensors' own rows as well as the sky's. that is a crossing between two modules and a
    deliberate one: both are plain daily aggregates with no decision attached, pairing them is the whole
    point of the chart, and a second use case in front of them would only read the same rows again.
    """

    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar):
        super().__init__(uow)
        self.household_calendar = household_calendar

    async def __call__(self, days: int, rooms: frozenset[str]) -> ClimateHistory:
        last_day = self.household_calendar.today() - timedelta(days=1)
        first_day = last_day - timedelta(days=days - 1)
        async with self.uow as uow:
            outdoor = [
                _read_day(row)
                for row in await uow.outdoor_weather_days.list_between(first_day, last_day)
                if row.reading_count >= LEAST_READINGS_FOR_A_DAY
            ]
            by_day: dict[date, list] = {}
            for room in sorted(rooms):
                for row in await uow.sensor_days.list_room_between(room, first_day, last_day):
                    if row.reading_count >= LEAST_READINGS_FOR_A_DAY and row.average_temperature_celsius is not None:
                        by_day.setdefault(row.day, []).append(row)

        return ClimateHistory(
            indoor=tuple(_fold_rooms(day, rows) for day, rows in sorted(by_day.items())),
            outdoor=tuple(outdoor),
        )


def _read_day(row) -> ClimateDay:
    return ClimateDay(
        day=row.day,
        minimum_celsius=row.minimum_temperature_celsius,
        maximum_celsius=row.maximum_temperature_celsius,
        average_celsius=row.average_temperature_celsius,
        average_humidity_percent=row.average_humidity_percent,
    )


def _fold_rooms(day: date, rows: list) -> ClimateDay:
    """One day of the whole flat, each number the middle room rather than the warmest or the coldest."""
    humidity = [row.average_humidity_percent for row in rows if row.average_humidity_percent is not None]
    return ClimateDay(
        day=day,
        minimum_celsius=median(row.minimum_temperature_celsius for row in rows),
        maximum_celsius=median(row.maximum_temperature_celsius for row in rows),
        average_celsius=median(row.average_temperature_celsius for row in rows),
        average_humidity_percent=median(humidity) if humidity else None,
    )
