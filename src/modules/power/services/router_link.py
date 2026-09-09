from typing import Protocol


class RouterLink(Protocol):
    """Answers the only question the router can be asked about itself: whether it is still there"""

    async def is_alive(self) -> bool:
        ...
