from typing import Protocol

from src.modules.weather.domain import LocalAirQuality


class LocalAirQualitySource(Protocol):
    """Reads PM2.5 from sensors near the flat — None when none of them answers"""

    async def read(self) -> LocalAirQuality | None:
        ...
