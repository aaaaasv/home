from typing import Protocol

from src.modules.weather.domain import WeatherReport


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
