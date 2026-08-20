from typing import Protocol

from src.common.domain import DomainModel


class RoomClimate(DomainModel):
    temperature_celsius: float
    relative_humidity_percent: float


class RoomClimateSensor(Protocol):
    """Reads the air the plants actually live in — returns None when the reading cannot be trusted"""

    async def read(self) -> RoomClimate | None:
        ...


class NullRoomClimateSensor:
    """The bot runs without a sensor attached, which is the normal state until one is wired in"""

    async def read(self) -> RoomClimate | None:
        return None
