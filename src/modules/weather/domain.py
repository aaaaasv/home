from datetime import date
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
    # the european index, modelled at ~11 km — useful as a fallback, but it cannot see a fire two streets
    # away. LocalAirQuality below is what replaces it whenever a real sensor nearby is answering
    european_air_quality_index: int | None
    pm2_5_micrograms: float | None
    pollen: list[PollenReading]


class LocalAirQuality(DomainModel):
    """
    PM2.5 as actually measured a few streets away, rather than modelled over a third of the city.

    measured 2–10.09.2026 from the sensors near this flat: median 1.6 µg/m³, above the WHO guideline 1.1% of
    the time, and one hour at 29.6 with a peak of 102. that shape — clean almost always, rare sharp spikes —
    is exactly what an 11 km model averages away, and the only reason this source exists.

    `sensor_count` is kept because these are hobby sensors: one of them reading oddly is common, and a median
    over several is worth more than a single number. it also tells a reader how much to trust the value.
    """

    pm2_5_micrograms: float
    sensor_count: int


class ClimateDay(DomainModel):
    """One finished day of air, indoors or out, in the shape a chart can draw without knowing which."""

    day: date
    minimum_celsius: float
    maximum_celsius: float
    average_celsius: float
    # the sensors in the rooms carry it and the sky usually does; a day without it still has a temperature
    average_humidity_percent: float | None = None


class ClimateHistory(DomainModel):
    """
    The two records side by side, each as long as it happens to be.

    they do not start on the same day and are not made to: the sky has been written down since the weather
    module learned to keep it, the rooms since their sensors went in, and a chart that waited for the shorter
    one would show nothing for weeks. so each series carries its own days and the drawing lines them up.
    """

    indoor: tuple[ClimateDay, ...] = ()
    outdoor: tuple[ClimateDay, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.indoor and not self.outdoor
