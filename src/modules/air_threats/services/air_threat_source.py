from typing import Protocol

from src.modules.air_threats.domain import AirThreat


class AirThreatSource(Protocol):
    """Whoever tracks what is in the air — returns None when the answer cannot be trusted, never a guess."""

    async def read_active(self) -> list[AirThreat] | None:
        ...


class NullAirThreatSource:
    """The bot runs without a threat map attached, which is the normal state until one is configured"""

    async def read_active(self) -> list[AirThreat] | None:
        return None
