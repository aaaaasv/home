"""The slow safety net behind the alert socket.

Everything that matters arrives by push. This exists for the one failure the socket cannot report about
itself: a connection that is open, subscribed and silent looks exactly like a calm night. That happened on
25.09.2026 and only a second, independent source caught it — so something has to ask on a clock as well.

The clock also owns the other half of the strip's life: putting it back out a quarter of an hour after it
went up. That is why the job must drive **the same watcher object** the socket drives, and not one of its own.
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.bot.scheduling import SchedulerContext


def register_jobs(scheduler: AsyncIOScheduler, context: SchedulerContext) -> None:
    """Nothing to watch without the watcher the composition root builds for the socket."""
    settings = context.settings
    if not settings.ALERT_LIGHT_ENABLED or context.air_alert_watcher is None:
        return

    scheduler.add_job(
        context.air_alert_watcher.__call__,
        trigger=IntervalTrigger(seconds=settings.ALERT_LIGHT_CHECK_SECONDS),
        id="alert_light_check",
        replace_existing=True,
    )
