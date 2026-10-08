from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.weather.domain import WeatherReport


class RecordOutdoorWeatherUseCase(BaseUseCase):
    """
    Folds one reading of the air outside into today's row.

    the indoor side has been kept per room per day since `sensor_days`; the outdoor side was fetched for
    every digest and dropped. the pair is what makes a flat legible — how fast each room loses heat, when the
    heating actually came on, what a four-hour January outage will do to the bedroom — and none of it can be
    recovered afterwards, so the row is written long before anything reads it.

    the day's own row is rewritten as the day fills, the same way a sensor's is: the last write is the day.
    """

    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar):
        super().__init__(uow)
        self.household_calendar = household_calendar

    async def __call__(self, report: WeatherReport) -> None:
        day = self.household_calendar.today()
        async with self.uow as uow:
            existing = await uow.outdoor_weather_days.retrieve_day(day)
            await uow.outdoor_weather_days.save_day(day, _fold(existing, report))


def _fold(existing, report: WeatherReport) -> dict:
    count = (existing.reading_count if existing else 0) + 1
    return {
        "reading_count": count,
        "minimum_temperature_celsius": _lowest(existing, "minimum_temperature_celsius", report.temperature_celsius),
        "maximum_temperature_celsius": _highest(existing, "maximum_temperature_celsius", report.temperature_celsius),
        "average_temperature_celsius": _averaged(
            existing, "average_temperature_celsius", report.temperature_celsius, count
        ),
        "minimum_humidity_percent": _lowest(existing, "minimum_humidity_percent", report.relative_humidity_percent),
        "maximum_humidity_percent": _highest(existing, "maximum_humidity_percent", report.relative_humidity_percent),
        "average_humidity_percent": _averaged(
            existing, "average_humidity_percent", report.relative_humidity_percent, count
        ),
    }


def _lowest(existing, field: str, value: float | None) -> float | None:
    previous = getattr(existing, field, None) if existing else None
    if value is None:
        return previous
    return value if previous is None else min(previous, value)


def _highest(existing, field: str, value: float | None) -> float | None:
    previous = getattr(existing, field, None) if existing else None
    if value is None:
        return previous
    return value if previous is None else max(previous, value)


def _averaged(existing, field: str, value: float | None, count: int) -> float | None:
    """A running mean, so a day never has to hold the readings it was folded from."""
    previous = getattr(existing, field, None) if existing else None
    if value is None:
        return previous
    if previous is None:
        return value
    return previous + (value - previous) / count
