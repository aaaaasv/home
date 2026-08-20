import asyncio
import logging
from datetime import datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

import aiohttp

from src.common.time import current_time
from src.modules.weather.domain import PollenReading, PollenSpecies, RainWindow, WeatherReport

logger = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
REQUEST_TIMEOUT_SECONDS = 15
# the outdoor weather barely moves minute to minute, so /ac buttons reuse the last fetch instead of blocking on a
# fresh network call — the live fetch happens only when the card is first opened (or the digest refreshes)
WEATHER_RECENT_MAX_AGE_SECONDS = 1800

# the window spans the hours around the peak that stay at least this share of it — a flat 20% floor would swallow
# the whole afternoon on a drizzly day, while a share tracks how pronounced the peak actually is
RAIN_WINDOW_PEAK_SHARE = 0.5

# wmo codes 95/96/99 are thunderstorm, with and without hail
THUNDERSTORM_CODES = frozenset({95, 96, 99})
# the hour people are home and deciding what the evening feels like
EVENING_HOUR = 21

# open-meteo exposes pollen only in the hourly block, and only inside the european cams domain (kyiv is inside it)
POLLEN_HOURLY_FIELDS: dict[PollenSpecies, str] = {
    PollenSpecies.RAGWEED: "ragweed_pollen",
    PollenSpecies.GRASS: "grass_pollen",
    PollenSpecies.BIRCH: "birch_pollen",
    PollenSpecies.ALDER: "alder_pollen",
    PollenSpecies.MUGWORT: "mugwort_pollen",
}


class WeatherProvider(Protocol):
    """Fetches the outdoor forecast and air quality — returns None when the reading cannot be trusted"""

    async def fetch(self) -> WeatherReport | None:
        ...

    def recent(self) -> WeatherReport | None:
        """The last successful fetch if it is still fresh, without touching the network — None otherwise"""
        ...


class NullWeatherProvider:
    async def fetch(self) -> WeatherReport | None:
        return None

    def recent(self) -> WeatherReport | None:
        return None


class OpenMeteoWeatherProvider:
    def __init__(self, latitude: float, longitude: float, timezone_name: str):
        self.latitude = latitude
        self.longitude = longitude
        self.timezone_name = timezone_name
        self._cached_report: WeatherReport | None = None
        self._cached_at: datetime | None = None

    async def fetch(self) -> WeatherReport | None:
        try:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                forecast = await self._get_json(session, FORECAST_URL, self._forecast_parameters())
                air_quality = await self._get_json(session, AIR_QUALITY_URL, self._air_quality_parameters())
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            logger.warning("Weather fetch failed: %r", error)
            return None

        report = parse_weather_report(forecast, air_quality, datetime.now(ZoneInfo(self.timezone_name)).hour)
        if report is not None:
            self._cached_report = report
            self._cached_at = current_time()
        return report

    def recent(self) -> WeatherReport | None:
        if self._cached_report is None or self._cached_at is None:
            return None
        if current_time() - self._cached_at > timedelta(seconds=WEATHER_RECENT_MAX_AGE_SECONDS):
            return None
        return self._cached_report

    def _forecast_parameters(self) -> dict:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "timezone": self.timezone_name,
            "forecast_days": 1,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m",
            "daily": "uv_index_max",
            "hourly": "precipitation_probability,wind_speed_10m,temperature_2m,weather_code",
            "wind_speed_unit": "ms",
        }

    def _air_quality_parameters(self) -> dict:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "timezone": self.timezone_name,
            "forecast_days": 1,
            "current": "european_aqi,pm2_5",
            "hourly": ",".join(POLLEN_HOURLY_FIELDS.values()),
        }

    async def _get_json(self, session: aiohttp.ClientSession, url: str, parameters: dict) -> dict:
        async with session.get(url, params=parameters) as response:
            response.raise_for_status()
            return await response.json()


def parse_weather_report(forecast: dict, air_quality: dict, current_hour: int) -> WeatherReport:
    current = forecast["current"]
    daily = forecast["daily"]
    hourly = forecast.get("hourly", {})
    air_quality_current = air_quality.get("current", {})
    air_quality_hourly = air_quality.get("hourly", {})
    peak_probability, rain_window = resolve_rain_outlook(hourly, current_hour)
    codes_ahead = read_hours_ahead(hourly, "weather_code", current_hour)
    # past the last forecast hour there is no day left to describe, so the current reading is the whole range
    temperatures_ahead = read_hours_ahead(hourly, "temperature_2m", current_hour) or [
        (current_hour, current["temperature_2m"])
    ]

    pollen = []
    for species, field in POLLEN_HOURLY_FIELDS.items():
        readings = [value for value in air_quality_hourly.get(field, []) if value is not None]
        if readings:
            pollen.append(PollenReading(species=species, grains_per_cubic_meter=max(readings)))

    return WeatherReport(
        temperature_celsius=current["temperature_2m"],
        apparent_temperature_celsius=current.get("apparent_temperature"),
        relative_humidity_percent=current.get("relative_humidity_2m"),
        temperature_max_celsius=max(value for _, value in temperatures_ahead),
        temperature_min_celsius=min(value for _, value in temperatures_ahead),
        temperature_evening_celsius=_temperature_at(temperatures_ahead, EVENING_HOUR),
        uv_index_max=_first_or_none(daily.get("uv_index_max")),
        is_thunderstorm_expected=any(code in THUNDERSTORM_CODES for _, code in codes_ahead),
        wind_speed_meters_per_second=resolve_peak_wind_speed(hourly, current_hour),
        precipitation_probability_percent=peak_probability,
        rain_window=rain_window,
        european_air_quality_index=_optional_int(air_quality_current.get("european_aqi")),
        pm2_5_micrograms=air_quality_current.get("pm2_5"),
        pollen=pollen,
    )


def read_hours_ahead(hourly: dict, field: str, current_hour: int) -> list[tuple[int, float]]:
    """(hour, value) pairs for the hours still to come today — what already happened must not shape the forecast"""
    return [
        (int(time_text[11:13]), value)
        for time_text, value in zip(hourly.get("time", []), hourly.get(field, []))
        if value is not None and int(time_text[11:13]) >= current_hour
    ]


def resolve_peak_wind_speed(hourly: dict, current_hour: int) -> float | None:
    hours = read_hours_ahead(hourly, "wind_speed_10m", current_hour)
    if not hours:
        return None

    return max(speed for _, speed in hours)


def resolve_rain_outlook(hourly: dict, current_hour: int) -> tuple[int | None, RainWindow | None]:
    """The peak chance over the hours still to come, and the stretch of hours it spans"""
    hours = read_hours_ahead(hourly, "precipitation_probability", current_hour)
    if not hours:
        return None, None

    peak_probability = max(probability for _, probability in hours)
    if peak_probability == 0:
        return peak_probability, None

    peak_index = next(index for index, (_, probability) in enumerate(hours) if probability == peak_probability)
    threshold = peak_probability * RAIN_WINDOW_PEAK_SHARE
    start_index = peak_index
    while start_index > 0 and hours[start_index - 1][1] >= threshold:
        start_index -= 1
    end_index = peak_index
    while end_index < len(hours) - 1 and hours[end_index + 1][1] >= threshold:
        end_index += 1

    return peak_probability, RainWindow(start_hour=hours[start_index][0], end_hour=hours[end_index][0])


def _temperature_at(temperatures_ahead: list[tuple[int, float]], hour: int) -> float | None:
    for candidate_hour, value in temperatures_ahead:
        if candidate_hour == hour:
            return value
    return None


def _first_or_none(values: list | None):
    if not values:
        return None
    return values[0]


def _optional_int(value) -> int | None:
    if value is None:
        return None
    return round(value)
