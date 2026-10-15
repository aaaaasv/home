"""The scheduled work that posts the morning weather digest, keeps it current, logs the day and draws it."""
import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path

from aiogram import Bot
from aiogram.types import BufferedInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.bot.handlers.weather.board import WEATHER_DIGEST_MISFIRE_GRACE_SECONDS
from src.bot.handlers.weather.chart import find_chart_font, render_climate_chart
from src.bot.scheduling import SchedulerContext
from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.bot.services.posted_message_tracker import CLIMATE_CHART_KIND, PostedMessageTracker
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.weather.use_cases.compose_climate_history import ComposeClimateHistoryUseCase
from src.modules.weather.use_cases.record_outdoor_weather import RecordOutdoorWeatherUseCase

logger = logging.getLogger(__name__)

# open-meteo sheds load exactly on the hour and the half hour, when every */15 cron in the world
# reaches it at once. every 503 the bot has recorded landed on :00 or :30 and none on :15 or :45,
# so the refresh is shifted off the boundary
REFRESH_OFFSET_MINUTES = 7
# the chart goes up a couple of minutes behind the digest, so it lands under it rather than racing it
CHART_OFFSET_MINUTES = 2
CHART_FILE_NAME = "climate.png"


def build_refresh_minutes(every_minutes: int, offset: int = REFRESH_OFFSET_MINUTES) -> str:
    """The cron minutes for a refresh of the given cadence, shifted off the hour boundary."""
    return ",".join(str((offset + step) % 60) for step in range(0, 60, every_minutes))


def register_jobs(scheduler: AsyncIOScheduler, context: SchedulerContext) -> None:
    """Three separate things share this topic, so each one asks about itself rather than about the digest."""
    _register_digest(scheduler, context)
    _register_outdoor_weather_log(scheduler, context)
    _register_climate_chart(scheduler, context)


def _register_digest(scheduler: AsyncIOScheduler, context: SchedulerContext) -> None:
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


class ClimateChartJob:
    """
    One picture a morning: the month behind us, the rooms against the sky.

    it is a photo and not another block of text because what it is for is the *shape* of a month — that the
    flat is drifting down a degree a week while the street falls five — and no arrangement of numbers in a
    message says that in one glance.

    only the newest one stands: the chart is redrawn from the same rows every morning, so yesterday's is
    not a record of anything, just an older copy of the same picture.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        weather_topic: ForumTopicRegistry,
        uow_factory: Callable[[], UnitOfWork],
        household_calendar: HouseholdCalendar,
        fonts: tuple[Path, Path],
        rooms: frozenset[str],
        days: int,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.weather_topic = weather_topic
        self.uow_factory = uow_factory
        self.household_calendar = household_calendar
        self.fonts = fonts
        self.rooms = rooms
        self.days = days
        self.tracker = PostedMessageTracker(bot=bot, uow_factory=uow_factory)

    async def __call__(self) -> None:
        history = await ComposeClimateHistoryUseCase(
            uow=self.uow_factory(), household_calendar=self.household_calendar
        )(days=self.days, rooms=self.rooms)
        picture = render_climate_chart(history, self.fonts)
        if picture is None:
            # a flat whose sensors went in yesterday has nothing to draw, and says so by staying quiet
            logger.info("Not enough of a record to draw the climate chart yet")
            return

        await self.tracker.clear(CLIMATE_CHART_KIND)
        message = await self.bot.send_photo(
            chat_id=self.chat_id,
            message_thread_id=await self.weather_topic.resolve(),
            photo=BufferedInputFile(picture, filename=CHART_FILE_NAME),
            # a glance over morning coffee, never a reason to buzz a phone
            disable_notification=True,
        )
        await self.tracker.remember(CLIMATE_CHART_KIND, message)
        logger.info("Posted the climate chart: %d days indoors, %d outdoors", len(history.indoor), len(history.outdoor))


def _register_climate_chart(scheduler: AsyncIOScheduler, context: SchedulerContext) -> None:
    """Drawn only where there is a font to draw it with — the image carries none of its own."""
    settings = context.settings
    if not settings.WEATHER_CHART_ENABLED or context.weather_topic is None:
        return
    rooms = frozenset(settings.room_by_sensor.values())
    if not rooms:
        return
    fonts = find_chart_font()
    if fonts is None:
        logger.warning("No font on this machine, so the climate chart stays undrawn (apt: fonts-dejavu-core)")
        return

    job = ClimateChartJob(
        bot=context.bot,
        chat_id=settings.TELEGRAM_REMINDER_CHAT_ID,
        weather_topic=context.weather_topic,
        uow_factory=context.uow_factory,
        household_calendar=context.household_calendar,
        fonts=fonts,
        rooms=rooms,
        days=settings.WEATHER_CHART_DAYS,
    )
    # a couple of minutes past the digest, carried over the hour rather than wrapped around it
    posted_at = (
        datetime.combine(date.min, settings.weather_digest_time) + timedelta(minutes=CHART_OFFSET_MINUTES)
    ).time()
    scheduler.add_job(
        job.__call__,
        trigger=CronTrigger(hour=posted_at.hour, minute=posted_at.minute),
        misfire_grace_time=WEATHER_DIGEST_MISFIRE_GRACE_SECONDS,
        id="climate_chart",
        replace_existing=True,
    )
