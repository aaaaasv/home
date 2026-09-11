from typing import Protocol

from src.modules.system_health.domain import DiskReading


class DiskHealthSource(Protocol):
    """Reads SMART from a machine that is not this one — None when it cannot be reached"""

    async def read(self) -> list[DiskReading] | None:
        ...
