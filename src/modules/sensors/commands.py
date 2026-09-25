from pydantic import BaseModel, Field


class RecordSensorReadingCommand(BaseModel):
    """
    What one sensor said once. Every measurement is optional because sensors differ in what they can say.

    there is no timestamp here on purpose: the broker carries none, a battery device's own clock is not to
    be trusted, and only the household calendar is allowed to say what "now" is.
    """

    sensor: str = Field(min_length=1, max_length=48)
    room: str | None = Field(default=None, max_length=32)
    temperature_celsius: float | None = None
    relative_humidity_percent: float | None = None
    soil_moisture_percent: float | None = None
    battery_percent: float | None = None
