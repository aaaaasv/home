from datetime import date, datetime

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
