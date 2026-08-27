from typing import Protocol

from src.modules.transit.domain import RealtimeSnapshot


class RealtimeFeed(Protocol):
    """Fetches live vehicle positions — returns None when the feed cannot be reached"""

    async def fetch(self) -> RealtimeSnapshot | None:
        ...
