"""The hourly fold: a day of raw readings becomes one row, and the raw ones past the window are let go."""
import logging
from collections.abc import Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.bot.scheduling import SchedulerContext
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.sensors.use_cases.fold_sensor_days import FoldSensorDaysUseCase

logger = logging.getLogger(__name__)


class FoldSensorDaysJob:
    """
    Keeps the sensor history affordable.

    it exists as a job rather than as part of recording because the sensors report on change: a single busy
    sensor can write tens of rows an hour, and re-reading a whole day on each of them would cost more than
    everything else the bot does put together.
    """

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        household_calendar: HouseholdCalendar,
        raw_retention_days: int,
    ):
        self.uow_factory = uow_factory
        self.household_calendar = household_calendar
        self.raw_retention_days = raw_retention_days

    async def __call__(self) -> None:
        folded = await FoldSensorDaysUseCase(
            uow=self.uow_factory(),
            household_calendar=self.household_calendar,
            raw_retention_days=self.raw_retention_days,
        )()
        logger.info("Folded %s sensor-day summaries", folded)


def register_jobs(scheduler: AsyncIOScheduler, context: SchedulerContext) -> None:
    """Nothing to fold until a sensor is mapped to a room or a pot, so an unmapped house schedules nothing."""
    settings = context.settings
    if not settings.recorded_sensors:
        return

    fold_job = FoldSensorDaysJob(
        uow_factory=context.uow_factory,
        household_calendar=context.household_calendar,
        raw_retention_days=settings.SENSOR_HISTORY_RAW_DAYS,
    )
    scheduler.add_job(
        fold_job.__call__,
        trigger=IntervalTrigger(minutes=settings.SENSOR_FOLD_INTERVAL_MINUTES),
        id="fold_sensor_days",
        replace_existing=True,
    )
