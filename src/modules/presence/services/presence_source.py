from typing import Protocol


class PresenceSource(Protocol):
    """Returns the MAC addresses currently connected to the network — None when the source cannot be reached"""

    async def online_macs(self) -> set[str] | None:
        ...


class NullPresenceSource:
    """No router access configured — presence stays unknown and the bot runs fine without it"""

    async def online_macs(self) -> set[str] | None:
        return None
