from typing import Protocol

from src.modules.power.domain import EcoFlowState


class EcoFlowStation(Protocol):
    """Talks to the EcoFlow Delta 2 over local ble — returns None when it is unreachable or not configured"""

    async def start(self) -> None:
        ...

    async def stop(self) -> None:
        ...

    async def read_state(self, refresh: bool = False) -> EcoFlowState | None:
        ...

    async def apply(
        self,
        ac_output: bool | None = None,
        usb_output: bool | None = None,
        dc_output: bool | None = None,
        charge_limit_max: int | None = None,
    ) -> EcoFlowState | None:
        ...


class NullEcoFlowStation:
    """No station configured — the bot must run fine in a flat that has none"""

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def read_state(self, refresh: bool = False) -> EcoFlowState | None:
        return None

    async def apply(
        self,
        ac_output: bool | None = None,
        usb_output: bool | None = None,
        dc_output: bool | None = None,
        charge_limit_max: int | None = None,
    ) -> EcoFlowState | None:
        return None
