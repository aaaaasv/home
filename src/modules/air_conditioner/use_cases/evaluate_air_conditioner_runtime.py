from datetime import datetime, timedelta

from src.common.use_case import BaseUseCase
from src.modules.air_conditioner.domain import AirConditionerRuntimeNotice, AirConditionerState


class EvaluateAirConditionerRuntimeUseCase(BaseUseCase):
    """
    Keeps one open row per continuous run and reports a run that has outlasted the threshold.

    it announces once per run rather than on every check: a unit left on all weekend is one mistake, not
    forty-eight of them, and a job that repeats itself is the one people mute.
    """

    def __init__(self, uow, notify_after: timedelta):
        super().__init__(uow)
        self.notify_after = notify_after

    async def __call__(self, state: AirConditionerState | None, moment: datetime) -> AirConditionerRuntimeNotice | None:
        async with self.uow as uow:
            open_run = await uow.air_conditioner_runs.retrieve_open()

            if state is None or not state.is_on:
                if open_run is not None:
                    open_run.ended_at = moment
                    await uow.commit()
                return None

            if open_run is None:
                await uow.air_conditioner_runs.create({"started_at": moment})
                await uow.commit()
                return None

            running_for = moment - open_run.started_at
            if running_for < self.notify_after or open_run.notified_at is not None:
                return None

            open_run.notified_at = moment
            await uow.commit()
            return AirConditionerRuntimeNotice(
                hours=int(running_for.total_seconds() // 3600),
                room_temperature_celsius=state.room_temperature_celsius,
            )
