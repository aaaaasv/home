from datetime import date, datetime
from statistics import fmean

from src.common.domain import DomainModel


class SensorMeasurement(DomainModel):
    """The latest thing a sensor said, as anything that shows a reading needs it."""

    sensor: str
    room: str | None
    measured_at: datetime
    temperature_celsius: float | None
    relative_humidity_percent: float | None
    soil_moisture_percent: float | None
    battery_percent: float | None


class SensorDaySummary(DomainModel):
    """What one sensor saw across one household day, once the raw readings are gone."""

    sensor: str
    room: str | None
    day: date
    reading_count: int
    minimum_temperature_celsius: float | None
    maximum_temperature_celsius: float | None
    average_temperature_celsius: float | None
    minimum_humidity_percent: float | None
    maximum_humidity_percent: float | None
    average_humidity_percent: float | None
    minimum_soil_moisture_percent: float | None
    maximum_soil_moisture_percent: float | None
    average_soil_moisture_percent: float | None
    minimum_battery_percent: float | None


class SensorNow(DomainModel):
    """One sensor's latest word, with whether it is old enough to distrust."""

    sensor: str
    room: str | None
    measured_at: datetime
    temperature_celsius: float | None
    relative_humidity_percent: float | None
    soil_moisture_percent: float | None
    battery_percent: float | None
    is_stale: bool


class ClimateSnapshot(DomainModel):
    """
    The flat as its sensors see it at one moment.

    air and soil are kept apart because averaging them would describe nowhere: a probe in a dry pot and a
    probe in one watered this morning have no meaningful middle, while room air genuinely does.
    """

    air: list[SensorNow]
    soil: list[SensorNow]
    taken_at: datetime

    @property
    def average_temperature_celsius(self) -> float | None:
        return average_of(one.temperature_celsius for one in self.air if not one.is_stale)

    @property
    def average_humidity_percent(self) -> float | None:
        return average_of(one.relative_humidity_percent for one in self.air if not one.is_stale)


class ClimateTrend(DomainModel):
    """How the flat's air compares with itself a day and a week ago, averaged across the rooms."""

    temperature_change_since_yesterday: float | None
    temperature_change_since_last_week: float | None
    humidity_change_since_yesterday: float | None
    humidity_change_since_last_week: float | None


def average_of(values) -> float | None:
    """The mean of whatever is actually there — a sensor with nothing to say must not drag the answer down."""
    present = [value for value in values if value is not None]
    return fmean(present) if present else None


class TemperatureSpan(DomainModel):
    """How far one sensor's temperature travelled over the last twenty-four hours."""

    sensor: str
    minimum_celsius: float
    maximum_celsius: float
