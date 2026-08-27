"""The scheduled work that keeps the route geometry cached so a card render never waits on a download."""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.bot.scheduling import SchedulerContext
from src.common.time import current_time


def register_jobs(scheduler: AsyncIOScheduler, context: SchedulerContext) -> None:
    """Refresh the static route shapes weekly, well away from anyone waiting for an arrival board."""
    settings = context.settings
    if not settings.TRANSIT_ENABLED or context.shape_catalog is None:
        return

    # the static host is slow and flaky, so geometry refreshes on its own weekly cadence (and once on boot,
    # where a fresh cache makes it a no-op) — a card render never waits on this download
    scheduler.add_job(
        context.shape_catalog.refresh,
        trigger=IntervalTrigger(days=settings.TRANSIT_STATIC_REFRESH_DAYS),
        next_run_time=current_time(),
        misfire_grace_time=3600,
        id="transit_static_refresh",
        replace_existing=True,
    )
