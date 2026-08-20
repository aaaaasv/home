from enum import StrEnum

from src.common.domain import DomainModel


class PollenSpecies(StrEnum):
    RAGWEED = "ragweed"
    GRASS = "grass"
    BIRCH = "birch"
    ALDER = "alder"
    MUGWORT = "mugwort"


class PollenReading(DomainModel):
    species: PollenSpecies
    # the day's peak grains per cubic metre — a morning digest cares about how bad it will get, not the 08:00 value
    grains_per_cubic_meter: float


class RainWindow(DomainModel):
    """The stretch of hours around the day's remaining peak, as local hours-of-day (both ends inclusive)"""

    start_hour: int
    end_hour: int


class VentilationEffect(StrEnum):
    DRIER = "drier"
    WETTER = "wetter"


class WeatherReport(DomainModel):
    temperature_celsius: float
    apparent_temperature_celsius: float | None
    relative_humidity_percent: float | None
    # both taken over the hours still ahead — the day's own max/min routinely fall before the morning digest
    temperature_max_celsius: float
    temperature_min_celsius: float
    temperature_evening_celsius: float | None
    uv_index_max: float | None
    is_thunderstorm_expected: bool
    # the strongest sustained wind still ahead today, in metres per second
    wind_speed_meters_per_second: float | None
    # the peak over the hours still ahead — the daily max would announce a shower that fell while everyone slept
    precipitation_probability_percent: int | None
    rain_window: RainWindow | None
    european_air_quality_index: int | None
    pm2_5_micrograms: float | None
    pollen: list[PollenReading]
