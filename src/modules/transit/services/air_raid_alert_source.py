from typing import Protocol


class AirRaidAlertSource(Protocol):
    """Whether the air-raid alert is active for the city — None when the status cannot be read"""

    async def is_alert_active(self) -> bool | None:
        ...
