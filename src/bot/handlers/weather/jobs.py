"""The scheduled work that posts the morning weather digest and keeps it current."""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.bot.handlers.weather.board import WEATHER_DIGEST_MISFIRE_GRACE_SECONDS
from src.bot.scheduling import SchedulerContext

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
