from typing import Protocol

from src.modules.air_conditioner.domain import AirConditionerFanSpeed, AirConditionerMode, AirConditionerState


class AirConditioner(Protocol):
    """Talks to the indoor unit over the local network — returns None when it cannot be reached"""

    @property
    def busy(self) -> bool:
        """True while one command is in flight, so a caller can drop a duplicate tap instead of queueing another"""
        ...

    async def read_state(self) -> AirConditionerState | None:
        ...

    async def apply(
        self,
        is_on: bool | None = None,
        mode: AirConditionerMode | None = None,
        target_temperature_celsius: int | None = None,
        fan_speed: AirConditionerFanSpeed | None = None,
        turbo: bool | None = None,
        quiet: bool | None = None,
        xfan: bool | None = None,
    ) -> AirConditionerState | None:
        ...


class NullAirConditioner:
    """No unit configured — the bot must run fine in a flat that has none"""

    busy = False

    async def read_state(self) -> AirConditionerState | None:
        return None

    async def apply(
        self,
        is_on: bool | None = None,
        mode: AirConditionerMode | None = None,
        target_temperature_celsius: int | None = None,
        fan_speed: AirConditionerFanSpeed | None = None,
        turbo: bool | None = None,
        quiet: bool | None = None,
        xfan: bool | None = None,
    ) -> AirConditionerState | None:
        return None
