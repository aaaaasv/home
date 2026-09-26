from typing import Protocol

from src.modules.air_alert.domain import AirAlert


class AirAlertSource(Protocol):
    """Whoever knows whether there is an alert here — None when it cannot be trusted, never a guess."""

    async def read_current(self) -> AirAlert | None:
        ...


class NullAirAlertSource:
    """The bot runs without an alert feed, which is the normal state until one is configured"""

    async def read_current(self) -> AirAlert | None:
        return None
