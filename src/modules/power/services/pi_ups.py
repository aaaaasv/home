from typing import Protocol

from src.modules.power.domain import UpsState


class PiUps(Protocol):
    """Reads the hat the pi itself runs on — returns None when the board cannot be reached"""

    async def read_state(self) -> UpsState | None:
        ...


class NullPiUps:
    """No hat fitted, which is how the bot runs everywhere except this flat"""

    async def read_state(self) -> UpsState | None:
        return None
