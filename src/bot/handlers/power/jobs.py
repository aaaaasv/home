"""The scheduled jobs that poll the station and the outage schedule."""
import logging
from collections.abc import Callable
from datetime import datetime, timedelta, tzinfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.bot.handlers.power.messages import POWER_OUTAGE_EMERGENCY, POWER_OUTAGE_SOON
from src.bot.handlers.power.outage_schedule_board import OutageScheduleBoard
from src.bot.scheduling import SchedulerContext
from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.bot.services.posted_message_tracker import OUTAGE_EMERGENCY_KIND, OUTAGE_PING_KIND, PostedMessageTracker
from src.common.config import Settings
from src.common.time import current_time
from src.infrastructure.db.uow import UnitOfWork
from src.modules.power.services.ecoflow_station import EcoFlowStation
from src.modules.power.services.yasno_schedule_provider import (
    OutageSchedule,
    OutageScheduleStatus,
    YasnoScheduleProvider,
)
from src.modules.power.use_cases.track_conservation import TrackConservationUseCase

logger = logging.getLogger(__name__)


class EcoFlowPollJob:
    """
    Samples the held-open ble link on an interval to track the storage regime (the /eco card reads the link live,
    not here). a reachable station refreshes the last-known charge and watches its trace for a completed 60→0→100→60
    cycle; a link that has stayed down long enough means the station is shelved (conserved) — a brief drop does not
    count. a manual /conserve mark wins until the station's own reachability confirms it.
    """

    def __init__(
        self,
        ecoflow_station: EcoFlowStation,
        uow_factory: Callable[[], UnitOfWork],
        timezone: tzinfo,
        conserved_after: timedelta,
    ):
        self.ecoflow_station = ecoflow_station
        self.uow_factory = uow_factory
        self.timezone = timezone
        self.conserved_after = conserved_after

    async def __call__(self) -> None:
        state = await self.ecoflow_station.read_state()
        if state is None:
            logger.info("EcoFlow poll: station not reachable over ble")
        else:
            logger.info(
                "EcoFlow poll: %s%% · %s", round(state.battery_percent), "on mains" if state.on_mains else "on battery"
            )
        await TrackConservationUseCase(
            uow=self.uow_factory(), now=datetime.now(self.timezone), conserved_after=self.conserved_after
        )(state)


class YasnoScheduleJob:
    """
    Every ~20 min: re-read the outage schedule, keep the daily board current (silent), and fire the only two pushes
    this topic allows — one heads-up ~30 min before each planned outage, and one alert a day when the group turns to
    emergency shutdowns. facts only, no advice; quiet whenever nothing is planned.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        power_topic: ForumTopicRegistry,
        uow_factory: Callable[[], UnitOfWork],
        schedule_provider: YasnoScheduleProvider,
        outage_schedule_board: OutageScheduleBoard,
        settings: Settings,
        timezone: tzinfo,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.power_topic = power_topic
        self.uow_factory = uow_factory
        self.schedule_provider = schedule_provider
        self.outage_schedule_board = outage_schedule_board
        self.settings = settings
        self.timezone = timezone
        self.tracker = PostedMessageTracker(bot=bot, uow_factory=uow_factory)

    async def __call__(self) -> None:
        outlook = await self.schedule_provider.fetch()
        if outlook is None:
            logger.info("Yasno schedule fetch failed; leaving the board as it is")
            return

        today = outlook.today
        # keep the board current: edit the day's message in place, or post the first one when an outage appears
        if not await self.outage_schedule_board.refresh(today) and today.has_outages:
            await self.outage_schedule_board.post(today)

        if today.status == OutageScheduleStatus.EMERGENCY_SHUTDOWNS:
            await self._push_emergency(today)
        await self._ping_upcoming_outage(today)

    async def _push_emergency(self, today: OutageSchedule) -> None:
        reference = today.day.isoformat()
        if await self._already_posted(OUTAGE_EMERGENCY_KIND, reference):
            return
        message = await self.bot.send_message(
            chat_id=self.chat_id,
            message_thread_id=await self.power_topic.resolve(),
            text=POWER_OUTAGE_EMERGENCY,
            # an emergency shutdown can hit any moment — the one push a day that earns a ping here
            disable_notification=False,
        )
        await self.tracker.remember(OUTAGE_EMERGENCY_KIND, message, reference=reference)
        logger.info("Announced emergency shutdowns for %s", reference)

    async def _ping_upcoming_outage(self, today: OutageSchedule) -> None:
        now = datetime.now(self.timezone)
        upcoming = today.next_off_interval(now)
        if upcoming is None:
            return
        minutes_until = upcoming.start_minute - (now.hour * 60 + now.minute)
        if not 0 < minutes_until <= self.settings.YASNO_PRE_OUTAGE_LEAD_MINUTES:
            return

        # one ping per interval per day, so a 20-min poll cannot announce the same outage twice
        reference = f"{today.day.isoformat()}:{upcoming.start_minute}"
        if await self._already_posted(OUTAGE_PING_KIND, reference):
            return
        message = await self.bot.send_message(
            chat_id=self.chat_id,
            message_thread_id=await self.power_topic.resolve(),
            text=POWER_OUTAGE_SOON.format(
                minutes=minutes_until, start=f"{upcoming.start:%H:%M}", end=f"{upcoming.end:%H:%M}"
            ),
            # a planned outage about to start — a real heads-up, worth a ping
            disable_notification=False,
        )
        await self.tracker.remember(OUTAGE_PING_KIND, message, reference=reference)
        logger.info("Pinged upcoming outage %s", reference)

    async def _already_posted(self, kind: str, reference: str) -> bool:
        async with self.uow_factory() as uow:
            return bool(await uow.posted_messages.list_by_reference(kind, reference))


def register_jobs(scheduler: AsyncIOScheduler, context: SchedulerContext) -> None:
    """Poll the station on its own cadence and follow the outage schedule on its — each switched on separately."""
    _register_station_jobs(scheduler, context)
    _register_outage_schedule_jobs(scheduler, context)


def _register_station_jobs(scheduler: AsyncIOScheduler, context: SchedulerContext) -> None:
    settings = context.settings
    if not settings.ECOFLOW_ENABLED or context.ecoflow_station is None:
        return

    ecoflow_poll_job = EcoFlowPollJob(
        ecoflow_station=context.ecoflow_station,
        uow_factory=context.uow_factory,
        timezone=settings.timezone,
        conserved_after=timedelta(minutes=settings.ECOFLOW_CONSERVED_AFTER_MINUTES),
    )
    # no boot run: the held-open link needs a moment to come up, and a None read before it does would read as
    # "shelved" — the first sample at +interval lands after the link is established
    scheduler.add_job(
        ecoflow_poll_job.__call__,
        trigger=IntervalTrigger(minutes=settings.ECOFLOW_POLL_MINUTES),
        id="ecoflow_poll",
        replace_existing=True,
    )
    # the conservation regime rides on those same ble reads — its card only speaks while the station is shelved
    if context.conservation_board is not None:
        scheduler.add_job(
            context.conservation_board.refresh,
            trigger=IntervalTrigger(hours=settings.ECOFLOW_CONSERVATION_CHECK_HOURS),
            next_run_time=current_time(),
            misfire_grace_time=120,
            id="ecoflow_conservation",
            replace_existing=True,
        )


def _register_outage_schedule_jobs(scheduler: AsyncIOScheduler, context: SchedulerContext) -> None:
    settings = context.settings
    if (
        not settings.YASNO_ENABLED
        or context.power_topic is None
        or context.schedule_provider is None
        or context.outage_schedule_board is None
    ):
        return

    # a fresh board each morning — silent when nothing is planned
    yasno_digest_time = settings.yasno_digest_time
    scheduler.add_job(
        context.outage_schedule_board.post,
        trigger=CronTrigger(hour=yasno_digest_time.hour, minute=yasno_digest_time.minute),
        id="outage_schedule_post",
        replace_existing=True,
    )
    yasno_job = YasnoScheduleJob(
        bot=context.bot,
        chat_id=settings.TELEGRAM_REMINDER_CHAT_ID,
        power_topic=context.power_topic,
        uow_factory=context.uow_factory,
        schedule_provider=context.schedule_provider,
        outage_schedule_board=context.outage_schedule_board,
        settings=settings,
        timezone=settings.timezone,
    )
    scheduler.add_job(
        yasno_job.__call__,
        trigger=IntervalTrigger(minutes=settings.YASNO_POLL_MINUTES),
        # run once on boot (grace window so a slow startup does not skip it), so a mid-day restart catches an outage
        next_run_time=current_time(),
        misfire_grace_time=120,
        id="yasno_schedule",
        replace_existing=True,
    )
