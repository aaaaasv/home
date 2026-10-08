"""The scheduled work that posts the morning weather digest, keeps it current, and logs the day."""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.bot.handlers.weather.board import WEATHER_DIGEST_MISFIRE_GRACE_SECONDS
from src.bot.scheduling import SchedulerContext
from src.modules.weather.use_cases.record_outdoor_weather import RecordOutdoorWeatherUseCase

logger = logging.getLogger(__name__)

# open-meteo sheds load exactly on the hour and the half hour, when every */15 cron in the world
# reaches it at once. every 503 the bot has recorded landed on :00 or :30 and none on :15 or :45,
# so the refresh is shifted off the boundary
REFRESH_OFFSET_MINUTES = 7


def build_refresh_minutes(every_minutes: int, offset: int = REFRESH_OFFSET_MINUTES) -> str:
    """The cron minutes for a refresh of the given cadence, shifted off the hour boundary."""
    return ",".join(str((offset + step) % 60) for step in range(0, 60, every_minutes))


def register_jobs(scheduler: AsyncIOScheduler, context: SchedulerContext) -> None:
    """Post one digest each morning, then edit it in place through the waking hours rather than posting again."""
    settings = context.settings
    if not settings.WEATHER_DIGEST_ENABLED or context.weather_digest_board is None:
        return

    digest_time = settings.weather_digest_time
    scheduler.add_job(
        context.weather_digest_board.post,
        trigger=CronTrigger(hour=digest_time.hour, minute=digest_time.minute),
        misfire_grace_time=WEATHER_DIGEST_MISFIRE_GRACE_SECONDS,
        id="weather_digest",
        replace_existing=True,
    )
    _register_outdoor_weather_log(scheduler, context)
    # keep the morning digest current in place: a silent edit every N minutes, only during waking hours
    scheduler.add_job(
        context.weather_digest_board.refresh,
        trigger=CronTrigger(
            minute=build_refresh_minutes(settings.WEATHER_REFRESH_MINUTES),
            hour=f"{settings.WEATHER_REFRESH_START_HOUR}-{settings.WEATHER_REFRESH_END_HOUR}",
        ),
        id="weather_refresh",
        replace_existing=True,
    )


class RecordOutdoorWeatherJob:
    """Folds the sky into today's row, around the clock — a night is what a heat-loss reading is made of."""

    def __init__(self, weather_provider, uow_factory, household_calendar):
        self.weather_provider = weather_provider
        self.uow_factory = uow_factory
        self.household_calendar = household_calendar

    async def __call__(self) -> None:
        report = await self.weather_provider.fetch()
        if report is None:
            # a missed hour is a thinner average, not a wrong one; open-meteo sheds load and comes back
            logger.info("The sky did not answer; today's row keeps the readings it already has")
            return
        await RecordOutdoorWeatherUseCase(uow=self.uow_factory(), household_calendar=self.household_calendar)(report)


def _register_outdoor_weather_log(scheduler: AsyncIOScheduler, context: SchedulerContext) -> None:
    """Hourly, all twenty-four of them — the digest sleeps at night and the night is half the measurement."""
    if context.weather_provider is None:
        return

    job = RecordOutdoorWeatherJob(
        weather_provider=context.weather_provider,
        uow_factory=context.uow_factory,
        household_calendar=context.household_calendar,
    )
    scheduler.add_job(
        job.__call__,
        trigger=CronTrigger(minute=REFRESH_OFFSET_MINUTES),
        id="outdoor_weather_log",
        replace_existing=True,
    )
