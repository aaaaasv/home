from typing import Protocol

from src.modules.room_climate.domain import RoomClimate


class RoomClimateSensor(Protocol):
    """Reads the air of the room — returns None when the reading cannot be trusted"""

    async def read(self) -> RoomClimate | None:
        ...


class NullRoomClimateSensor:
    """The bot runs without a sensor attached, which is the normal state until one is wired in"""

    async def read(self) -> RoomClimate | None:
        return None
