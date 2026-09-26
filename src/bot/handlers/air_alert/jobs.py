"""The slow safety net behind the alert socket.

Everything that matters arrives by push. This exists for the one failure the socket cannot report about
itself: a connection that is open, subscribed and silent looks exactly like a calm night. That happened on
25.09.2026 and only a second, independent source caught it — so something has to ask on a clock as well.
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.bot.handlers.air_alert.light import AlertLightWatcher
from src.bot.scheduling import SchedulerContext

logger = logging.getLogger(__name__)


def register_jobs(scheduler: AsyncIOScheduler, context: SchedulerContext) -> None:
    """Nothing to watch without a feed and a light — either missing and the module stays off."""
    settings = context.settings
    if not settings.ALERT_LIGHT_ENABLED or context.air_alert_source is None or context.panel_light is None:
        return

    watcher = AlertLightWatcher(
        uow_factory=context.uow_factory,
        source=context.air_alert_source,
        panel_light=context.panel_light,
        settings=settings,
        household_calendar=context.household_calendar,
    )
    scheduler.add_job(
        watcher.__call__,
        trigger=IntervalTrigger(seconds=settings.ALERT_LIGHT_CHECK_SECONDS),
        id="alert_light_check",
        replace_existing=True,
    )
