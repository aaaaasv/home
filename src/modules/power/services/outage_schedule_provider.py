from typing import Protocol

from src.modules.power.domain import OutageOutlook, OutageSchedule


class OutageScheduleProvider(Protocol):
    """The planned-outage picture for the household's group — None whenever it cannot be trusted"""

    async def fetch(self) -> OutageOutlook | None:
        ...

    async def fetch_today(self) -> OutageSchedule | None:
        ...
