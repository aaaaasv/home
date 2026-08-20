from datetime import timedelta

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.bot.handlers.air_conditioner.jobs import AirConditionerRuntimeJob
from src.bot.handlers.chores.jobs import ChoreDeadlineJob
from src.bot.handlers.plants.jobs import DailyCareDigestJob, RoomClimateJob
from src.bot.handlers.power.conservation_board import ConservationBoard
from src.bot.handlers.power.jobs import EcoFlowPollJob, YasnoScheduleJob
from src.bot.handlers.power.outage_schedule_board import OutageScheduleBoard
from src.bot.handlers.presence.jobs import PresenceJob
from src.bot.handlers.shopping.jobs import PriceWatchJob
from src.bot.handlers.system.jobs import SystemHealthJob
from src.bot.handlers.weather.board import WEATHER_DIGEST_MISFIRE_GRACE_SECONDS, WeatherDigestBoard
from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.bot.services.posted_message_tracker import PostedMessageTracker
from src.common.config import Settings
from src.common.household_calendar import HouseholdCalendar
from src.common.time import current_time
from src.infrastructure.db.uow import UnitOfWork
from src.modules.air_conditioner.services.air_conditioner import AirConditioner
from src.modules.plant_care.services.room_climate_sensor import RoomClimateSensor
from src.modules.power.services.ecoflow_station import EcoFlowStation
from src.modules.power.services.yasno_schedule_provider import YasnoScheduleProvider
from src.modules.presence.services.presence_source import PresenceSource
from src.modules.shopping.services.price_source import PriceSource
from src.modules.system_health.services.pi_health_sensor import PiHealthSensor
from src.modules.transit.services.route_shape_catalog import RouteShapeCatalog


def build_scheduler(
    bot: Bot,
    settings: Settings,
    household_calendar: HouseholdCalendar,
    care_topic: ForumTopicRegistry,
    shopping_topic: ForumTopicRegistry,
    chores_topic: ForumTopicRegistry,
    room_climate_sensor: RoomClimateSensor,
    price_source: PriceSource,
    weather_topic: ForumTopicRegistry | None = None,
    weather_digest_board: WeatherDigestBoard | None = None,
    air_conditioner: AirConditioner | None = None,
    tech_topic: ForumTopicRegistry | None = None,
    pi_health_sensor: PiHealthSensor | None = None,
    presence_source: PresenceSource | None = None,
    ecoflow_station: EcoFlowStation | None = None,
    power_topic: ForumTopicRegistry | None = None,
    schedule_provider: YasnoScheduleProvider | None = None,
    outage_schedule_board: OutageScheduleBoard | None = None,
    conservation_board: ConservationBoard | None = None,
    shape_catalog: RouteShapeCatalog | None = None,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    if settings.CLIMATE_SENSOR_ENABLED:
        climate_job = RoomClimateJob(
            bot=bot,
            chat_id=settings.TELEGRAM_REMINDER_CHAT_ID,
            care_topic=care_topic,
            uow_factory=UnitOfWork,
            sensor=room_climate_sensor,
            settings=settings,
            posted_message_tracker=PostedMessageTracker(bot=bot, uow_factory=UnitOfWork),
            household_calendar=household_calendar,
        )
        # pass the bound __call__, not the instance: apscheduler only awaits jobs it sees as coroutine functions,
        # and a callable instance is not one — passing the instance runs it sync and drops the coroutine unawaited
        scheduler.add_job(
            climate_job.__call__,
            trigger=IntervalTrigger(seconds=settings.CLIMATE_SAMPLE_INTERVAL_SECONDS),
            id="room_climate",
            replace_existing=True,
        )
        # once a day (and once on boot), repost each still-uncomfortable plant's card silently at the bottom,
        # so a standing alert that scrolled away stays visible without a second ping
        scheduler.add_job(
            climate_job.refresh_discomfort_cards,
            trigger=CronTrigger(hour=settings.daily_digest_time.hour, minute=settings.daily_digest_time.minute),
            next_run_time=current_time(),
            id="plant_discomfort_refresh",
            replace_existing=True,
        )

    digest_job = DailyCareDigestJob(
        bot=bot,
        chat_id=settings.TELEGRAM_REMINDER_CHAT_ID,
        care_topic=care_topic,
        uow_factory=UnitOfWork,
        household_calendar=household_calendar,
        settings=settings,
        posted_message_tracker=PostedMessageTracker(bot=bot, uow_factory=UnitOfWork),
    )
    scheduler.add_job(
        digest_job.__call__,
        trigger=IntervalTrigger(minutes=settings.DIGEST_CHECK_INTERVAL_MINUTES),
        # fire once right after start too, so a digest missed while the pi was down is caught up on boot
        next_run_time=current_time(),
        id="daily_care_digest",
        replace_existing=True,
    )

    if settings.WEATHER_DIGEST_ENABLED and weather_digest_board is not None:
        digest_time = settings.weather_digest_time
        scheduler.add_job(
            weather_digest_board.post,
            trigger=CronTrigger(hour=digest_time.hour, minute=digest_time.minute),
            misfire_grace_time=WEATHER_DIGEST_MISFIRE_GRACE_SECONDS,
            id="weather_digest",
            replace_existing=True,
        )
        # keep the morning digest current in place: a silent edit every N minutes, only during waking hours
        scheduler.add_job(
            weather_digest_board.refresh,
            trigger=CronTrigger(
                minute=f"*/{settings.WEATHER_REFRESH_MINUTES}",
                hour=f"{settings.WEATHER_REFRESH_START_HOUR}-{settings.WEATHER_REFRESH_END_HOUR}",
            ),
            id="weather_refresh",
            replace_existing=True,
        )

    if settings.AIR_CONDITIONER_ENABLED and weather_topic is not None and air_conditioner is not None:
        runtime_job = AirConditionerRuntimeJob(
            bot=bot,
            chat_id=settings.TELEGRAM_REMINDER_CHAT_ID,
            weather_topic=weather_topic,
            uow_factory=UnitOfWork,
            air_conditioner=air_conditioner,
            settings=settings,
        )
        scheduler.add_job(
            runtime_job.__call__,
            trigger=IntervalTrigger(minutes=settings.AIR_CONDITIONER_CHECK_MINUTES),
            id="air_conditioner_runtime",
            replace_existing=True,
        )

    if settings.ECOFLOW_ENABLED and ecoflow_station is not None:
        ecoflow_poll_job = EcoFlowPollJob(
            ecoflow_station=ecoflow_station,
            uow_factory=UnitOfWork,
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
        if conservation_board is not None:
            scheduler.add_job(
                conservation_board.refresh,
                trigger=IntervalTrigger(hours=settings.ECOFLOW_CONSERVATION_CHECK_HOURS),
                next_run_time=current_time(),
                misfire_grace_time=120,
                id="ecoflow_conservation",
                replace_existing=True,
            )

    if (
        settings.YASNO_ENABLED
        and power_topic is not None
        and schedule_provider is not None
        and outage_schedule_board is not None
    ):
        # a fresh board each morning — silent when nothing is planned
        yasno_digest_time = settings.yasno_digest_time
        scheduler.add_job(
            outage_schedule_board.post,
            trigger=CronTrigger(hour=yasno_digest_time.hour, minute=yasno_digest_time.minute),
            id="outage_schedule_post",
            replace_existing=True,
        )
        yasno_job = YasnoScheduleJob(
            bot=bot,
            chat_id=settings.TELEGRAM_REMINDER_CHAT_ID,
            power_topic=power_topic,
            uow_factory=UnitOfWork,
            schedule_provider=schedule_provider,
            outage_schedule_board=outage_schedule_board,
            settings=settings,
            timezone=settings.timezone,
        )
        # re-read on an interval and fire the pings; run once on boot so a mid-day restart still catches an outage
        scheduler.add_job(
            yasno_job.__call__,
            trigger=IntervalTrigger(minutes=settings.YASNO_POLL_MINUTES),
            # run once on boot (grace window so a slow startup does not skip it), so a mid-day restart catches an outage
            next_run_time=current_time(),
            misfire_grace_time=120,
            id="yasno_schedule",
            replace_existing=True,
        )

    if settings.TRANSIT_ENABLED and shape_catalog is not None:
        # the static host is slow and flaky, so geometry refreshes on its own weekly cadence (and once on boot,
        # where a fresh cache makes it a no-op) — a card render never waits on this download
        scheduler.add_job(
            shape_catalog.refresh,
            trigger=IntervalTrigger(days=settings.TRANSIT_STATIC_REFRESH_DAYS),
            next_run_time=current_time(),
            misfire_grace_time=3600,
            id="transit_static_refresh",
            replace_existing=True,
        )

    if settings.SYSTEM_HEALTH_ENABLED and tech_topic is not None and pi_health_sensor is not None:
        system_health_job = SystemHealthJob(
            bot=bot,
            chat_id=settings.TELEGRAM_REMINDER_CHAT_ID,
            tech_topic=tech_topic,
            sensor=pi_health_sensor,
            settings=settings,
        )
        scheduler.add_job(
            system_health_job.__call__,
            trigger=IntervalTrigger(minutes=settings.PI_HEALTH_CHECK_MINUTES),
            id="system_health",
            replace_existing=True,
        )

    if (
        settings.PRESENCE_ENABLED
        and weather_topic is not None
        and presence_source is not None
        and air_conditioner is not None
    ):
        presence_job = PresenceJob(
            bot=bot,
            chat_id=settings.TELEGRAM_REMINDER_CHAT_ID,
            weather_topic=weather_topic,
            presence_source=presence_source,
            air_conditioner=air_conditioner,
            settings=settings,
        )
        scheduler.add_job(
            presence_job.__call__,
            trigger=IntervalTrigger(minutes=settings.PRESENCE_CHECK_MINUTES),
            id="presence",
            replace_existing=True,
        )

    price_watch_job = PriceWatchJob(
        bot=bot,
        chat_id=settings.TELEGRAM_REMINDER_CHAT_ID,
        shopping_topic=shopping_topic,
        uow_factory=UnitOfWork,
        price_source=price_source,
        tech_topic=tech_topic,
    )
    price_watch_time = settings.price_watch_time
    scheduler.add_job(
        price_watch_job.__call__,
        trigger=CronTrigger(hour=price_watch_time.hour, minute=price_watch_time.minute),
        id="price_watch",
        replace_existing=True,
    )

    chore_deadline_job = ChoreDeadlineJob(
        bot=bot,
        chat_id=settings.TELEGRAM_REMINDER_CHAT_ID,
        chores_topic=chores_topic,
        uow_factory=UnitOfWork,
        household_calendar=household_calendar,
        settings=settings,
        posted_message_tracker=PostedMessageTracker(bot=bot, uow_factory=UnitOfWork),
    )
    # hourly, but only within waking hours — a deadline crossing pings at a civilized time, never at 03:00
    scheduler.add_job(
        chore_deadline_job.__call__,
        trigger=CronTrigger(minute=0, hour=f"{settings.CHORE_REMINDER_START_HOUR}-{settings.CHORE_REMINDER_END_HOUR}"),
        id="chore_deadlines",
        replace_existing=True,
    )
    return scheduler
