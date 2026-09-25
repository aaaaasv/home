from datetime import timedelta
from statistics import mean

from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.models import SensorReading
from src.infrastructure.db.uow import UnitOfWork


class FoldSensorDaysUseCase(BaseUseCase):
    """
    Folds each sensor's day into one row, then throws away raw readings older than the retention window.

    two days are folded, not one: the job runs on a clock and a day ends between runs, so the previous day is
    rewritten once more after it is complete. folding is a rewrite rather than an accumulation — the raw rows
    are still there, so recomputing cannot drift the way a running average can, and a pi that was down for an
    hour simply produces a summary of the hours it saw.
    """

    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar, raw_retention_days: int):
        super().__init__(uow)
        self.household_calendar = household_calendar
        self.raw_retention_days = raw_retention_days

    async def __call__(self) -> int:
        moment = self.household_calendar.now()
        today = self.household_calendar.local_date(moment)
        days = [today - timedelta(days=1), today]

        folded = 0
        async with self.uow as uow:
            for day in days:
                day_start = self.household_calendar.start_of_day(day)
                day_end = day_start + timedelta(days=1)
                for sensor in await uow.sensor_readings.list_sensors_measured_since(day_start):
                    readings = await uow.sensor_readings.list_measured_between(sensor, day_start, day_end)
                    if not readings:
                        continue
                    await uow.sensor_days.save_day(sensor, day, self._summarise(readings))
                    folded += 1

            # pruning last, and only after the fold has written every day it could: a raw row is allowed to
            # disappear once its day is summarised, never before
            await uow.sensor_readings.delete_measured_before(moment - timedelta(days=self.raw_retention_days))
        return folded

    def _summarise(self, readings: list[SensorReading]) -> dict:
        temperatures = [reading.temperature_celsius for reading in readings if reading.temperature_celsius is not None]
        humidities = [
            reading.relative_humidity_percent for reading in readings if reading.relative_humidity_percent is not None
        ]
        moistures = [reading.soil_moisture_percent for reading in readings if reading.soil_moisture_percent is not None]
        batteries = [reading.battery_percent for reading in readings if reading.battery_percent is not None]

        return {
            # the room is taken from the newest reading: a sensor moved to another room this morning belongs
            # to the room it is in now, not the one it woke up in
            "room": readings[-1].room,
            "reading_count": len(readings),
            "minimum_temperature_celsius": min(temperatures, default=None),
            "maximum_temperature_celsius": max(temperatures, default=None),
            "average_temperature_celsius": mean(temperatures) if temperatures else None,
            "minimum_humidity_percent": min(humidities, default=None),
            "maximum_humidity_percent": max(humidities, default=None),
            "average_humidity_percent": mean(humidities) if humidities else None,
            "minimum_soil_moisture_percent": min(moistures, default=None),
            "maximum_soil_moisture_percent": max(moistures, default=None),
            "average_soil_moisture_percent": mean(moistures) if moistures else None,
            "minimum_battery_percent": min(batteries, default=None),
        }
