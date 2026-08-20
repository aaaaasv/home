import logging
from datetime import datetime, timedelta

from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.power.domain import EcoFlowState
from src.modules.power.services.conservation import (
    CYCLE_DETECT_HIGH_PERCENT,
    CYCLE_DETECT_LOW_PERCENT,
    ConservationMode,
)

logger = logging.getLogger(__name__)


class TrackConservationUseCase(BaseUseCase):
    """
    Advances the storage regime from one station reading, reachable or not.

    a reachable station re-baselines the last known charge and has its trace watched for a completed 60→0→100→60
    cycle; a link that has stayed down long enough means the station is shelved, and a brief drop does not count.
    a manual /conserve mark wins until the station's own reachability confirms it.
    """

    def __init__(self, uow: UnitOfWork, now: datetime, conserved_after: timedelta):
        super().__init__(uow)
        self.now = now
        self.conserved_after = conserved_after

    async def __call__(self, state: EcoFlowState | None) -> None:
        async with self.uow as uow:
            record = await uow.conservation.get()

            if record is None:
                # wait for a first reading before baselining — an unseen, already-away station has no known charge
                if state is None:
                    return
                await uow.conservation.save(
                    {
                        "stored_percent": state.battery_percent,
                        "stored_at": self.now,
                        "mode": ConservationMode.OFF.value,
                        "is_conserved": False,
                        "manual_override": False,
                        "saw_low_since_cycle": state.battery_percent <= CYCLE_DETECT_LOW_PERCENT,
                    }
                )
                return

            data: dict = {}
            if state is not None:
                # we can see the charge, so the estimate is just the reading — re-baseline and watch for a cycle
                data["stored_percent"] = state.battery_percent
                data["stored_at"] = self.now
                saw_low = record.saw_low_since_cycle or state.battery_percent <= CYCLE_DETECT_LOW_PERCENT
                data["saw_low_since_cycle"] = saw_low
                if saw_low and state.battery_percent >= CYCLE_DETECT_HIGH_PERCENT:
                    # a full discharge to the floor and back to near-full — the calibration cycle just closed
                    data["last_cycle_at"] = self.now
                    data["saw_low_since_cycle"] = False
                    logger.info("EcoFlow maintenance cycle detected — clock reset")
                # a live read is proof it is in use: auto un-conserves, and confirms a manual "in use"
                if record.manual_override and not record.is_conserved:
                    data["manual_override"] = False
                elif not record.manual_override and record.is_conserved:
                    data["is_conserved"] = False
            else:
                # unreachable → conserved, but only once the link has stayed down long enough that a brief drop or a
                # restart caught mid-reconnect cannot trip it; stored_at is the last time we actually read the station
                conserved_long_enough = self.now - record.stored_at >= self.conserved_after
                if record.manual_override:
                    if record.is_conserved and conserved_long_enough:
                        data["manual_override"] = False
                elif not record.is_conserved and conserved_long_enough:
                    data["is_conserved"] = True
                    logger.info("EcoFlow conserved at ~%s%%", round(record.stored_percent))

            if data:
                await uow.conservation.save(data)
