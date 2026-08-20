from datetime import datetime

from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.power.services.conservation import STORAGE_TARGET_PERCENT, ConservationMode


class SetConservationModeUseCase(BaseUseCase):
    """
    Records the family's own «на зберігання» / «у користуванні» mark for the station.

    the mark carries a manual override, so a flaky read cannot undo it; only the station's real reachability does.
    marking it stored freezes the storage clock at this moment, since that is the last charge anyone can vouch for.
    """

    def __init__(self, uow: UnitOfWork, now: datetime):
        super().__init__(uow)
        self.now = now

    async def __call__(self, is_conserved: bool, battery_percent: float | None) -> None:
        async with self.uow as uow:
            record = await uow.conservation.get()
            data: dict = {"is_conserved": is_conserved, "manual_override": True}
            if is_conserved:
                # freeze the storage clock at this moment; while reachable the poll keeps the charge fresh anyway
                data["stored_at"] = self.now
            if record is None:
                data.update(
                    {
                        "stored_percent": (
                            battery_percent if battery_percent is not None else float(STORAGE_TARGET_PERCENT)
                        ),
                        "stored_at": self.now,
                        "mode": ConservationMode.OFF.value,
                        "saw_low_since_cycle": False,
                    }
                )
            await uow.conservation.save(data)
