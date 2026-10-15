"""The scheduled jobs that poll the station and the outage schedule."""
import logging
from collections.abc import Callable
from datetime import datetime, timedelta, tzinfo

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.bot.handlers.power.board import PowerBoard
from src.bot.handlers.power.formatting import render_mains_change, render_outage_forecast, render_outage_recovery
from src.bot.handlers.power.keyboards import build_supply_keyboard
from src.bot.handlers.power.messages import POWER_OUTAGE_SOON, POWER_SUPPLY_QUESTION
from src.bot.scheduling import SchedulerContext
from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.bot.services.posted_message_tracker import OUTAGE_EMERGENCY_KIND, OUTAGE_PING_KIND, PostedMessageTracker
from src.common.config import Settings
from src.common.household_calendar import HouseholdCalendar
from src.common.time import current_time
from src.infrastructure.db.uow import UnitOfWork
from src.modules.power.domain import (
    DeclaredSupply,
    EcoFlowState,
    GridChange,
    GridState,
    OutageForecast,
    OutageOutlook,
    OutageSchedule,
    OutageScheduleStatus,
    Reserve,
)
from src.modules.power.mains_monitor import MainsMonitor, classify_grid
from src.modules.power.outage_forecast import forecast_outage
from src.modules.power.services.ecoflow_station import EcoFlowStation
from src.modules.power.services.outage_schedule_provider import OutageScheduleProvider
from src.modules.power.services.pi_ups import PiUps
from src.modules.power.use_cases.declare_supply import DeclareSupplyUseCase
from src.modules.power.use_cases.record_grid_change import RecordGridChangeUseCase
from src.modules.power.use_cases.retrieve_declared_supply import RetrieveDeclaredSupplyUseCase
from src.modules.power.use_cases.revise_declared_supply import ReviseDeclaredSupplyUseCase
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
        household_calendar: HouseholdCalendar,
        timezone: tzinfo,
        conserved_after: timedelta,
    ):
        self.ecoflow_station = ecoflow_station
        self.uow_factory = uow_factory
        self.household_calendar = household_calendar
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
        await self._release_the_declaration(state)

    async def _release_the_declaration(self, state: EcoFlowState | None) -> None:
        """
        A station drawing from the wall proves that wall is live, which ends any claim that it is feeding us.

        without this the declaration would be a trap: «ні, це Delta 2» silences «світло є» until somebody
        remembers to take it back, and that is the one message the family actually waits for.
        """
        if state is None or state.ac_input_power <= 0:
            return
        if await RetrieveDeclaredSupplyUseCase(uow=self.uow_factory())() is DeclaredSupply.GRID:
            return

        await DeclareSupplyUseCase(uow=self.uow_factory(), household_calendar=self.household_calendar)(
            DeclaredSupply.GRID
        )
        logger.info("The station is charging from the wall, so the declaration that it feeds us is released")


class MainsWatchJob:
    """
    Watches the wall socket and speaks twice per outage: when it goes, and when it returns.

    this is the message the whole of layer 1 is built for, and the second half is the one the family waits for.
    it asks the pi's own hat and nothing else: that line is wired to the wall socket, so it measures the city
    rather than guessing at it. with the hat unreadable it stays silent, because a guess here reads exactly
    like a blackout — and the station's watts, which used to be that guess, cannot tell an unplugged station
    from a blackout at all.

    the monitor is seeded from the recorded events on the first tick, not on construction: the job is built
    while the scheduler is being assembled, long before anything may touch the database.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        power_topic: ForumTopicRegistry,
        pi_ups: PiUps,
        ecoflow_station: EcoFlowStation | None,
        settings: Settings,
        uow_factory: Callable[[], UnitOfWork],
        household_calendar: HouseholdCalendar,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.power_topic = power_topic
        self.pi_ups = pi_ups
        self.ecoflow_station = ecoflow_station
        self.uow_factory = uow_factory
        self.household_calendar = household_calendar
        self.monitor = MainsMonitor(confirmations=settings.ECOFLOW_MAINS_CONFIRMATIONS)
        self._declared_supply: DeclaredSupply | None = None

    async def __call__(self) -> None:
        # the hat is read before the declaration is asked for, because the reading is what can end it:
        # a station feeding the pi cannot leave its socket without mains
        ups = await self.pi_ups.read_state()
        declared_supply = await ReviseDeclaredSupplyUseCase(
            uow=self.uow_factory(), household_calendar=self.household_calendar
        )(ups)
        # the station's card going back to the grid — by hand, or because the hat contradicted it — is
        # already the answer to the question below, so the announcement it brings must not ask it again
        answered_by_hand = self._declared_supply is DeclaredSupply.STATION and declared_supply is DeclaredSupply.GRID
        self._declared_supply = declared_supply
        await self._seed_from_the_journal()
        grid = self.monitor.update(ups, declared_supply)
        if grid is None:
            return

        # written before the message is sent: a telegram outage must not cost the record of what happened,
        # and the record is also where the span in the message comes from
        change = await RecordGridChangeUseCase(uow=self.uow_factory(), household_calendar=self.household_calendar)(grid)
        text, keyboard = await self._compose(grid, change, may_ask=not answered_by_hand)

        await self.bot.send_message(
            chat_id=self.chat_id,
            message_thread_id=await self.power_topic.resolve(),
            text=text,
            reply_markup=keyboard,
            # the one push in this house that must arrive the moment it is sent
            disable_notification=False,
        )
        logger.info("Announced the grid going %s", grid.value)

    async def _compose(self, grid: GridState, change: GridChange, may_ask: bool = True):
        """
        The announcement, and the buttons that let a person correct the one thing the hat cannot measure.

        «світло є» always carries «ні, це Delta 2»: it is the only message that can be wrong, and the
        station is asleep or out of bluetooth range too often for «only when it contradicts» to be
        enough. the question above it appears only when the station really does contradict the hat.
        «світло зникло» carries nothing — the mark belongs on the board, where it is still reachable an
        hour later, which is when somebody switches back.
        """
        text = render_mains_change(grid, change.lasted)
        if grid is GridState.ON_BATTERY:
            # nothing to correct yet: the light really has gone, and the mark lives on the board now
            return text, None

        keyboard = build_supply_keyboard(DeclaredSupply.GRID, change.event_id)
        contradicting = await self._station_contradicting() if may_ask else None
        if contradicting is None:
            return text, keyboard
        question = POWER_SUPPLY_QUESTION.format(watts=contradicting.ac_output_power)
        return f"{text}\n\n{question}", build_supply_keyboard(DeclaredSupply.GRID, change.event_id, asking=True)

    async def _station_contradicting(self) -> EcoFlowState | None:
        """
        The station discharging into something while the hat sees mains — the one arrangement worth a question.

        a station drawing from the wall proves the wall is live and ends the matter; one that is neither
        charging nor feeding anything knows nothing worth asking about.
        """
        if self.ecoflow_station is None:
            return None
        state = await self.ecoflow_station.read_state()
        if state is None or state.ac_input_power > 0 or state.ac_output_power <= 0:
            return None
        return state

    async def _seed_from_the_journal(self) -> None:
        """
        Where the grid stood when this house last said something, read fresh every tick rather than once.

        the journal is the truth and this is only its cache: an announcement can be taken back by hand —
        «ні, це Delta 2» deletes the row it wrote — and a copy kept in memory would go on believing the
        light was back and never announce the real return.
        """
        async with self.uow_factory() as uow:
            latest = await uow.grid_events.retrieve_latest()
        self.monitor.seed(GridState(latest.state) if latest is not None else None)


class PowerBoardJob:
    """
    Keeps the board current, on the cadence the moment deserves.

    every tick while the flat is on battery — that is the hour anyone opens it, and a board an hour stale then
    is worse than none. on the grid the picture does not move minute to minute, so it is rewritten every few.
    the reading happens on every tick either way, because the reading is what decides which cadence applies,
    and it is three local calls rather than a fetch.
    """

    def __init__(self, power_board: PowerBoard, on_grid_interval: timedelta, timezone: tzinfo):
        self.power_board = power_board
        self.on_grid_interval = on_grid_interval
        self.timezone = timezone
        self._drawn_at: datetime | None = None

    async def __call__(self) -> None:
        reserve = await self.power_board.read_reserve()
        now = datetime.now(self.timezone)
        if not self._is_due(reserve, now):
            return

        self._drawn_at = now
        await self.power_board.draw(reserve)

    def _is_due(self, reserve: Reserve | None, now: datetime) -> bool:
        if self._drawn_at is None:
            return True
        if reserve is not None and reserve.grid is GridState.ON_BATTERY:
            return True
        return now - self._drawn_at >= self.on_grid_interval


class OutageForecastJob:
    """
    Says one thing, once per outage: that the battery will not last until the light is scheduled to return.

    it never announces good news unprompted. "you reach" is a fact worth nothing at the moment it is true and
    worth less every minute after, and a push that speaks on every outage is a push the family mutes. the one
    exception is taking its own warning back: that message is already on screen being read.

    the shortfall must survive two readings, because the station's runtime estimate follows the instantaneous
    draw — boiling a kettle collapses it from hours to minutes, and the first version of this job woke the
    family over three minutes of tea.

    the schedule is remembered rather than re-fetched, because the moment this question matters is the moment
    the internet may be gone too — and a forecast that only works while the grid is up forecasts nothing.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        power_topic: ForumTopicRegistry,
        ecoflow_station: EcoFlowStation,
        schedule_provider: OutageScheduleProvider,
        household_calendar: HouseholdCalendar,
        pi_ups: PiUps,
        uow_factory: Callable[[], UnitOfWork],
        confirmations: int = 2,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.power_topic = power_topic
        self.ecoflow_station = ecoflow_station
        self.schedule_provider = schedule_provider
        self.household_calendar = household_calendar
        self.pi_ups = pi_ups
        self.uow_factory = uow_factory
        self.confirmations = confirmations
        self._last_schedule: OutageSchedule | None = None
        self._warned = False
        self._seen_short = 0
        self._warning_message_id: int | None = None

    async def __call__(self) -> None:
        # the schedule counts minutes from local midnight, so the comparison has to happen in local time
        calendar = self.household_calendar
        moment = calendar.now().astimezone(calendar.timezone)
        state = await self.ecoflow_station.read_state()
        declared_supply = await RetrieveDeclaredSupplyUseCase(uow=self.uow_factory())()
        grid = classify_grid(await self.pi_ups.read_state(), declared_supply)
        forecast = forecast_outage(state, await self._schedule(moment), moment, grid)

        if forecast is None:
            # the grid is back, or the question cannot be answered — either way the next outage is a fresh one
            self._warned = False
            self._seen_short = 0
            self._warning_message_id = None
            return

        if forecast.reaches:
            self._seen_short = 0
            await self._take_the_warning_back(forecast)
            return

        self._seen_short += 1
        if self._warned or self._seen_short < self.confirmations:
            return

        self._warned = True
        sent = await self.bot.send_message(
            chat_id=self.chat_id,
            message_thread_id=await self.power_topic.resolve(),
            text=render_outage_forecast(forecast),
            # there is a deadline in this message, so it is worth interrupting for
            disable_notification=False,
        )
        self._warning_message_id = sent.message_id
        logger.info("Warned that the battery falls %s short of the scheduled return", forecast.shortfall)

    async def _take_the_warning_back(self, forecast: OutageForecast) -> None:
        """Rewrites the warning where it stands — a second push to say "never mind" is how a topic gets muted."""
        if self._warning_message_id is None:
            return

        message_id = self._warning_message_id
        self._warning_message_id = None
        # the load may rise again, and a second genuine shortfall has to be allowed to speak
        self._warned = False
        try:
            await self.bot.edit_message_text(
                chat_id=self.chat_id, message_id=message_id, text=render_outage_recovery(forecast)
            )
        except TelegramBadRequest as error:
            logger.info("Could not take the shortfall warning back: %s", error)
        else:
            logger.info("Took the shortfall warning back — the station reaches %s again", forecast.power_returns_at)

    async def _schedule(self, moment: datetime) -> OutageSchedule | None:
        schedule = await self.schedule_provider.fetch_today()
        if schedule is not None:
            self._last_schedule = schedule
        if self._last_schedule is not None and self._last_schedule.day == moment.date():
            return self._last_schedule
        return None


class YasnoScheduleJob:
    """
    Every ~20 min: re-read the outage schedule, keep the daily board current (silent), and fire the only two pushes
    this topic allows — one heads-up ~30 min before each planned outage, and one when the group turns to emergency
    shutdowns. facts only, no advice; quiet whenever nothing is planned.

    the heads-up also asks the hat whether there is anything to warn about: an outage that arrived early makes
    the announcement of the planned one read as though the light were still on.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        power_topic: ForumTopicRegistry,
        uow_factory: Callable[[], UnitOfWork],
        power_board: PowerBoard,
        pi_ups: PiUps | None,
        settings: Settings,
        timezone: tzinfo,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.power_topic = power_topic
        self.uow_factory = uow_factory
        self.power_board = power_board
        self.pi_ups = pi_ups
        self.settings = settings
        self.timezone = timezone
        self.tracker = PostedMessageTracker(bot=bot, uow_factory=uow_factory)

    async def __call__(self) -> None:
        # the board holds the provider and remembers what it last heard, so this is the only place that asks
        outlook = await self.power_board.read_outlook()
        if outlook is None:
            logger.info("Yasno schedule fetch failed; leaving the board as it is")
            return

        # the regime turning announces itself by reposting the board, so it speaks before the silent refresh
        if not await self._announce_emergency_regime(outlook):
            await self.power_board.draw()

        await self._ping_upcoming_outage(outlook.today)

    async def _announce_emergency_regime(self, outlook: OutageOutlook) -> bool:
        """
        Repost the board with a ping when the group goes onto emergency shutdowns — once, until it comes back off.

        there used to be a separate alert sentence here, and it said what the board's own banner says a line
        lower: two messages, one regime. the board is the thing worth reading, so it is the board that pings.

        it is also not keyed on the calendar day any more — a spell that lasted past midnight announced itself
        again at six minutes past, in the night, with news from that morning.
        """
        today = outlook.today
        is_emergency = today.status is OutageScheduleStatus.EMERGENCY_SHUTDOWNS
        announced = bool(await self._list_posted(OUTAGE_EMERGENCY_KIND))
        if not is_emergency:
            if announced:
                # forgotten, not deleted: the board stays where it is and goes back to refreshing silently
                await self.tracker.forget(OUTAGE_EMERGENCY_KIND)
                logger.info("Emergency shutdowns are over; the next spell will announce itself again")
            return False
        if announced:
            return False

        message = await self.power_board.post(notify=True)
        if message is None:
            return False
        await self.tracker.remember(OUTAGE_EMERGENCY_KIND, message, reference=today.day.isoformat())
        logger.info("Announced emergency shutdowns starting %s", today.day.isoformat())
        return True

    async def _list_posted(self, kind: str) -> list:
        async with self.uow_factory() as uow:
            return await uow.posted_messages.list_by_kind(kind)

    async def _ping_upcoming_outage(self, today: OutageSchedule) -> None:
        # the hours shown during emergency shutdowns are the operator's plan, which the operator itself says is
        # not in force — a heads-up for one of them would be wrong about as often as it was right
        if today.status is OutageScheduleStatus.EMERGENCY_SHUTDOWNS:
            return

        now = datetime.now(self.timezone)
        upcoming = today.next_off_interval(now)
        if upcoming is None:
            return
        minutes_until = upcoming.start_minute - (now.hour * 60 + now.minute)
        if not 0 < minutes_until <= self.settings.YASNO_PRE_OUTAGE_LEAD_MINUTES:
            return

        # «за 20 хв відключення» reads as a promise that the light is on now. on 14.10 it was cut at 12:19,
        # unscheduled, and this went off at 12:40 about the hour that was planned for 13:00
        if await self._the_light_is_already_out():
            logger.info("Skipped the heads-up for the %s outage: the light is already out", f"{upcoming.start:%H:%M}")
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

    async def _the_light_is_already_out(self) -> bool:
        """
        Whether the flat is on battery at this moment, measured rather than inferred.

        nothing is read into a hat that cannot answer: a flat without one keeps the heads-up it always had,
        because a missing reading is not an outage.
        """
        if self.pi_ups is None:
            return False
        declared_supply = await RetrieveDeclaredSupplyUseCase(uow=self.uow_factory())()
        return classify_grid(await self.pi_ups.read_state(), declared_supply) is GridState.ON_BATTERY

    async def _already_posted(self, kind: str, reference: str) -> bool:
        async with self.uow_factory() as uow:
            return bool(await uow.posted_messages.list_by_reference(kind, reference))


def register_jobs(scheduler: AsyncIOScheduler, context: SchedulerContext) -> None:
    """Poll the station on its own cadence and follow the outage schedule on its — each switched on separately."""
    _register_station_jobs(scheduler, context)
    _register_mains_watch(scheduler, context)
    _register_power_board(scheduler, context)
    _register_outage_schedule_jobs(scheduler, context)


def _register_mains_watch(scheduler: AsyncIOScheduler, context: SchedulerContext) -> None:
    """
    The grid is watched on its own, far tighter cadence: this is the one message worth being early.

    it needs the hat and only the hat. a flat with a station but no hat gets no grid messages at all, which
    is correct: the station cannot tell being unplugged from a blackout, so it has nothing to say here.
    """
    settings = context.settings
    if context.power_topic is None or not settings.PI_UPS_ENABLED or context.pi_ups is None:
        return

    mains_watch_job = MainsWatchJob(
        bot=context.bot,
        chat_id=settings.TELEGRAM_REMINDER_CHAT_ID,
        power_topic=context.power_topic,
        pi_ups=context.pi_ups,
        ecoflow_station=context.ecoflow_station,
        settings=settings,
        uow_factory=context.uow_factory,
        household_calendar=context.household_calendar,
    )
    scheduler.add_job(
        mains_watch_job.__call__,
        trigger=IntervalTrigger(minutes=settings.ECOFLOW_MAINS_CHECK_MINUTES),
        id="mains_watch",
        replace_existing=True,
    )


def _register_power_board(scheduler: AsyncIOScheduler, context: SchedulerContext) -> None:
    """
    A fresh board each morning, and the cadence that keeps it current while the flat is on battery.

    the morning repost is what keeps the card inside the 48 hours a bot may edit its own message for, and it
    is also why nothing has to repost the reserve separately — the two halves are one card now.
    """
    settings = context.settings
    if context.power_board is None:
        return

    # kept at the hour yasno usually publishes the day, because that is when the schedule half changes
    morning = settings.yasno_digest_time
    scheduler.add_job(
        context.power_board.post,
        trigger=CronTrigger(hour=morning.hour, minute=morning.minute),
        id="power_board_post",
        replace_existing=True,
    )
    # only the reserve half moves minute to minute; a schedule-only board has nothing to redraw that often
    if not settings.RESERVE_ENABLED or not context.power_board.draws_the_reserve:
        return

    power_board_job = PowerBoardJob(
        power_board=context.power_board,
        on_grid_interval=timedelta(minutes=settings.RESERVE_ON_GRID_REFRESH_MINUTES),
        timezone=settings.timezone,
    )
    # no boot run: the held-open ble link needs a moment to come up, and the first tick lands after it has
    scheduler.add_job(
        power_board_job.__call__,
        trigger=IntervalTrigger(minutes=settings.RESERVE_CHECK_MINUTES),
        id="power_board",
        replace_existing=True,
    )


def _register_station_jobs(scheduler: AsyncIOScheduler, context: SchedulerContext) -> None:
    settings = context.settings
    if not settings.ECOFLOW_ENABLED or context.ecoflow_station is None:
        return

    ecoflow_poll_job = EcoFlowPollJob(
        ecoflow_station=context.ecoflow_station,
        uow_factory=context.uow_factory,
        household_calendar=context.household_calendar,
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
    # the forecast needs the schedule to know when the light is due and the hat to know the light is still out,
    # so it registers only where both exist
    if context.power_topic is not None and context.schedule_provider is not None and context.pi_ups is not None:
        outage_forecast_job = OutageForecastJob(
            bot=context.bot,
            chat_id=settings.TELEGRAM_REMINDER_CHAT_ID,
            power_topic=context.power_topic,
            ecoflow_station=context.ecoflow_station,
            schedule_provider=context.schedule_provider,
            household_calendar=context.household_calendar,
            pi_ups=context.pi_ups,
            uow_factory=context.uow_factory,
        )
        scheduler.add_job(
            outage_forecast_job.__call__,
            trigger=IntervalTrigger(minutes=settings.ECOFLOW_FORECAST_CHECK_MINUTES),
            id="ecoflow_outage_forecast",
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
    if not settings.YASNO_ENABLED or context.power_topic is None or context.power_board is None:
        return

    yasno_job = YasnoScheduleJob(
        bot=context.bot,
        chat_id=settings.TELEGRAM_REMINDER_CHAT_ID,
        power_topic=context.power_topic,
        uow_factory=context.uow_factory,
        power_board=context.power_board,
        pi_ups=context.pi_ups,
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
