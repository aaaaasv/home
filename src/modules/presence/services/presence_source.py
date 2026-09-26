from typing import Protocol

from src.modules.presence.domain import NetworkClient


class PresenceSource(Protocol):
    """Reads the router's client list — None when the router cannot be reached, which is not the same as empty"""

    async def read_clients(self) -> list[NetworkClient] | None:
        ...


class NullPresenceSource:
    """No router access configured — presence stays unknown and the bot runs fine without it"""

    async def read_clients(self) -> list[NetworkClient] | None:
        return None
