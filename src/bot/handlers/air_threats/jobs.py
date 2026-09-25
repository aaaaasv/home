"""The slow tick that closes cards nobody will announce the end of.

Everything urgent comes through the socket the moment it happens. This exists only because a track fading
from the map is a passage of time rather than an event: no frame ever says «того дрона більше немає», so
something has to look on a clock. Hence a lazy interval — it is housekeeping, not warning.
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.bot.handlers.air_threats.watch import AirThreatWatcher
from src.bot.scheduling import SchedulerContext

logger = logging.getLogger(__name__)


def register_jobs(scheduler: AsyncIOScheduler, context: SchedulerContext) -> None:
    """Nothing to watch without a map, a place and somebody to tell — any one missing and the module stays off."""
    settings = context.settings
    if not settings.AIR_THREATS_ENABLED or context.air_threat_source is None or not settings.AIR_THREATS_CHAT_ID:
        return

    watcher = AirThreatWatcher(
        bot=context.bot,
        chat_id=settings.AIR_THREATS_CHAT_ID,
        uow_factory=context.uow_factory,
        source=context.air_threat_source,
        settings=settings,
        household_calendar=context.household_calendar,
    )
    scheduler.add_job(
        watcher.__call__,
        trigger=IntervalTrigger(seconds=settings.AIR_THREATS_SWEEP_SECONDS),
        id="air_threats_sweep",
        replace_existing=True,
    )
