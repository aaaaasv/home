from datetime import timedelta

from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.sensors.domain import TemperatureSpan

DAY = timedelta(days=1)


class MeasureTemperatureSpanUseCase(BaseUseCase):
    """
    The lowest and highest temperature each sensor saw over the last twenty-four hours.

    the window is rolling and read from raw readings on purpose, for the reason the trend uses one: the folded
    row for today holds only the day so far, so at eight in the morning it would call the night «за добу» and
    show a span that hides the afternoon peak the reader is asking about. a sensor that said nothing in the
    window, or never reported a temperature, has no span rather than a made-up one.
    """

    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar):
        super().__init__(uow)
        self.household_calendar = household_calendar

    async def __call__(self, sensors: set[str]) -> dict[str, TemperatureSpan]:
        now = self.household_calendar.now()
        spans: dict[str, TemperatureSpan] = {}
        async with self.uow as uow:
            for sensor in sensors:
                readings = await uow.sensor_readings.list_measured_between(sensor, now - DAY, now)
                temperatures = [
                    reading.temperature_celsius for reading in readings if reading.temperature_celsius is not None
                ]
                if temperatures:
                    spans[sensor] = TemperatureSpan(
                        sensor=sensor, minimum_celsius=min(temperatures), maximum_celsius=max(temperatures)
                    )
        return spans
