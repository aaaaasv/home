from typing import Protocol

from src.modules.system_health.domain import PiHealthReading


class PiHealthSensor(Protocol):
    """Reads the host pi's vitals — returns None when they cannot be read (e.g. not running on a pi)"""

    async def read(self) -> PiHealthReading | None:
        ...


class NullPiHealthSensor:
    """No monitoring configured — the bot must run fine off a pi too"""

    async def read(self) -> PiHealthReading | None:
        return None
