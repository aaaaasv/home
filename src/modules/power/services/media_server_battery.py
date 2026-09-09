from typing import Protocol

from src.modules.power.domain import MediaServerState


class MediaServerBattery(Protocol):
    """Reads the media server's own battery — returns None when the box cannot be reached"""

    async def read_state(self) -> MediaServerState | None:
        ...
