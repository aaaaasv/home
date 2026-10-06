"""The scheduled jobs that watch the Pi, the media server's disks and the sensors' batteries."""
import logging
from collections.abc import Callable

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.bot.handlers.system.formatting import (
    render_media_server_disk_alert,
    render_sensor_battery_card,
    render_shelf_heat_card,
    render_shelf_recovered,
    render_system_health_alert,
)
from src.bot.scheduling import SchedulerContext
from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.bot.services.posted_message_tracker import PostedMessageTracker
from src.common.config import Settings
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.use_cases.list_plants import ListPlantsUseCase
from src.modules.room_climate.services.room_climate_sensor import RoomClimateSensor
from src.modules.sensors.use_cases.retrieve_climate_snapshot import RetrieveClimateSnapshotUseCase
from src.modules.system_health.battery_monitor import SensorBatteryMonitor
from src.modules.system_health.disk_monitor import DiskHealthMonitor
from src.modules.system_health.monitor import SystemHealthMonitor
from src.modules.system_health.services.disk_health_source import DiskHealthSource
from src.modules.system_health.services.pi_health_sensor import PiHealthSensor
from src.modules.system_health.shelf_heat_monitor import ShelfHeatMonitor

logger = logging.getLogger(__name__)

# one standing card per sensor whose battery has run low, referenced by the sensor's name
SENSOR_BATTERY_KIND = "sensor_battery"
# one standing card for the shelf, its reference being the level already reported
SHELF_HEAT_KIND = "shelf_heat"


class SystemHealthJob:
    """
    Watches the pi's own vitals and speaks only when one crosses into trouble — under-voltage, overheating, or a
    filling disk. it posts to a technical topic no one else uses, and stays silent the rest of the time.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        tech_topic: ForumTopicRegistry,
        sensor: PiHealthSensor,
        settings: Settings,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.tech_topic = tech_topic
        self.sensor = sensor
        self.monitor = SystemHealthMonitor(
            temperature_alert_celsius=settings.PI_TEMPERATURE_ALERT_CELSIUS,
            temperature_recovery_celsius=settings.PI_TEMPERATURE_RECOVERY_CELSIUS,
            disk_alert_percent=settings.PI_DISK_ALERT_PERCENT,
            disk_recovery_percent=settings.PI_DISK_RECOVERY_PERCENT,
        )

    async def __call__(self) -> None:
        reading = await self.sensor.read()
        if reading is None:
            return

        issues = self.monitor.evaluate(reading)
        if not issues:
            return

        await self.bot.send_message(
            chat_id=self.chat_id,
            message_thread_id=await self.tech_topic.resolve(),
            text=render_system_health_alert(issues),
            # under-voltage or overheating can damage the pi and its card — worth a ping even in the tech topic
            disable_notification=False,
        )
        logger.info("Reported %s system health issue(s)", len(issues))


class MediaServerDiskJob:
    """
    Watches the media server's disks and speaks only when one of them starts to go.

    it exists because `smartd` on that machine already watches them continuously and then mails local root,
    which nobody has ever read. the watching was never the missing part — the telling was.

    the box is asleep, halted for a blackout, or simply off the network fairly often, and none of that is a
    disk fault, so an unreachable machine is silence rather than an alert.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        tech_topic: ForumTopicRegistry,
        disks: DiskHealthSource,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.tech_topic = tech_topic
        self.disks = disks
        self.monitor = DiskHealthMonitor()

    async def __call__(self) -> None:
        readings = await self.disks.read()
        if not readings:
            return

        issues = self.monitor.evaluate(readings)
        if not issues:
            return

        await self.bot.send_message(
            chat_id=self.chat_id,
            message_thread_id=await self.tech_topic.resolve(),
            text=render_media_server_disk_alert(issues),
            # a disk that has started reallocating is on a clock, and the archive lives on it — worth the ping
            disable_notification=False,
        )
        logger.info("Announced %d media server disk issue(s)", len(issues))


class SensorBatteryJob:
    """
    Tells the family once when a sensor's battery runs low, and takes the card down when a fresh cell is in.

    six zigbee sensors are six coin cells that fall off a cliff rather than a slope, and the only place the charge
    showed was /climate — which means going to look. a sensor with a flat battery goes quiet, and a quiet sensor
    reads as steady air. about three cards a year, each one worth the ping.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        tech_topic: ForumTopicRegistry,
        uow_factory: Callable[[], UnitOfWork],
        household_calendar: HouseholdCalendar,
        settings: Settings,
        posted_message_tracker: PostedMessageTracker,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.tech_topic = tech_topic
        self.uow_factory = uow_factory
        self.household_calendar = household_calendar
        self.settings = settings
        self.posted_message_tracker = posted_message_tracker
        self.monitor = SensorBatteryMonitor()

    async def __call__(self) -> None:
        snapshot = await RetrieveClimateSnapshotUseCase(
            uow=self.uow_factory(), household_calendar=self.household_calendar, rooms=self.settings.room_by_sensor
        )(soil_sensors=set(self.settings.plant_by_soil_sensor))
        async with self.uow_factory() as uow:
            carded = {posted.reference for posted in await uow.posted_messages.list_by_kind(SENSOR_BATTERY_KIND)}

        verdict = self.monitor.evaluate(snapshot.air + snapshot.soil, carded)
        if verdict.newly_low:
            plants = await ListPlantsUseCase(uow=self.uow_factory(), household_calendar=self.household_calendar)()
            plant_name_by_id = {plant.id: plant.name for plant in plants}
            topic_id = await self.tech_topic.resolve()
            for reading in verdict.newly_low:
                plant_id = self.settings.plant_by_soil_sensor.get(reading.sensor)
                posted = await self.bot.send_message(
                    chat_id=self.chat_id,
                    message_thread_id=topic_id,
                    text=render_sensor_battery_card(reading, plant_name_by_id.get(plant_id)),
                    # a cell this low is days to weeks from silence — the one moment worth a ping
                    disable_notification=False,
                )
                await self.posted_message_tracker.remember(SENSOR_BATTERY_KIND, posted, reference=reading.sensor)
                logger.info("Reported a low battery on sensor %s (%.0f%%)", reading.sensor, reading.battery_percent)

        for sensor in verdict.recovered:
            await self.posted_message_tracker.clear_one(SENSOR_BATTERY_KIND, sensor)


class ShelfHeatJob:
    """
    Watches the one sensor that stands where the heat is, and says so once per step up.

    the sht31 hangs off the pi on a short ribbon, so since the pi moved it has measured the server shelf rather
    than any room. that is not a defect to hide behind a rename: the shelf carries the router, the media laptop
    and the ups cells, and it is the place in the flat where a temperature is worth watching.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        tech_topic: ForumTopicRegistry,
        sensor: RoomClimateSensor,
        posted_message_tracker: PostedMessageTracker,
        uow_factory: Callable[[], UnitOfWork],
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.tech_topic = tech_topic
        self.sensor = sensor
        self.posted_message_tracker = posted_message_tracker
        self.uow_factory = uow_factory
        self.monitor = ShelfHeatMonitor()

    async def __call__(self) -> None:
        climate = await self.sensor.read()
        async with self.uow_factory() as uow:
            standing = await uow.posted_messages.list_by_kind(SHELF_HEAT_KIND)
        carded_level = standing[-1].reference if standing else None

        verdict = self.monitor.evaluate(climate, carded_level)
        if verdict.level is not None:
            await self.posted_message_tracker.clear(SHELF_HEAT_KIND)
            posted = await self.bot.send_message(
                chat_id=self.chat_id,
                message_thread_id=await self.tech_topic.resolve(),
                text=render_shelf_heat_card(verdict.level, climate.temperature_celsius),
                # hardware cooking quietly is exactly the case a silent message would waste
                disable_notification=False,
            )
            await self.posted_message_tracker.remember(SHELF_HEAT_KIND, posted, reference=verdict.level)
            logger.info("Server shelf at %.1f°C reported as %s", climate.temperature_celsius, verdict.level)
            return

        if verdict.recovered:
            await self.posted_message_tracker.clear(SHELF_HEAT_KIND)
            await self.bot.send_message(
                chat_id=self.chat_id,
                message_thread_id=await self.tech_topic.resolve(),
                text=render_shelf_recovered(climate.temperature_celsius),
                disable_notification=True,
            )
            logger.info("Server shelf back down to %.1f°C", climate.temperature_celsius)


def register_jobs(scheduler: AsyncIOScheduler, context: SchedulerContext) -> None:
    """Watch the Pi's vitals, the media server's disks and the sensors' batteries, once there is a tech topic."""
    settings = context.settings
    if not settings.SYSTEM_HEALTH_ENABLED or context.tech_topic is None:
        return

    if context.pi_health_sensor is not None:
        system_health_job = SystemHealthJob(
            bot=context.bot,
            chat_id=settings.TELEGRAM_REMINDER_CHAT_ID,
            tech_topic=context.tech_topic,
            sensor=context.pi_health_sensor,
            settings=settings,
        )
        scheduler.add_job(
            system_health_job.__call__,
            trigger=IntervalTrigger(minutes=settings.PI_HEALTH_CHECK_MINUTES),
            id="system_health",
            replace_existing=True,
        )
    _register_media_server_disks(scheduler, context)
    _register_sensor_batteries(scheduler, context)
    _register_shelf_heat(scheduler, context)


def _register_media_server_disks(scheduler: AsyncIOScheduler, context: SchedulerContext) -> None:
    """The probe on that machine refreshes hourly, so asking more often than that would only re-read a file."""
    if context.tech_topic is None or context.media_server_disks is None:
        return

    disk_job = MediaServerDiskJob(
        bot=context.bot,
        chat_id=context.settings.TELEGRAM_REMINDER_CHAT_ID,
        tech_topic=context.tech_topic,
        disks=context.media_server_disks,
    )
    scheduler.add_job(
        disk_job.__call__,
        trigger=IntervalTrigger(hours=context.settings.MEDIA_SERVER_DISK_CHECK_HOURS),
        id="media_server_disks",
        replace_existing=True,
    )


def _register_sensor_batteries(scheduler: AsyncIOScheduler, context: SchedulerContext) -> None:
    """A battery drains over weeks, so an hourly look is generous; the card is what keeps it from repeating."""
    battery_job = SensorBatteryJob(
        bot=context.bot,
        chat_id=context.settings.TELEGRAM_REMINDER_CHAT_ID,
        tech_topic=context.tech_topic,
        uow_factory=context.uow_factory,
        household_calendar=context.household_calendar,
        settings=context.settings,
        posted_message_tracker=context.build_posted_message_tracker(),
    )
    scheduler.add_job(
        battery_job.__call__,
        trigger=IntervalTrigger(hours=1),
        id="sensor_batteries",
        replace_existing=True,
    )


def _register_shelf_heat(scheduler: AsyncIOScheduler, context: SchedulerContext) -> None:
    """Only worth scheduling where the wired sensor exists — it is the one that stands on the shelf."""
    if context.tech_topic is None or not context.settings.CLIMATE_SENSOR_ENABLED:
        return

    shelf_job = ShelfHeatJob(
        bot=context.bot,
        chat_id=context.settings.TELEGRAM_REMINDER_CHAT_ID,
        tech_topic=context.tech_topic,
        sensor=context.room_climate_sensor,
        posted_message_tracker=context.build_posted_message_tracker(),
        uow_factory=context.uow_factory,
    )
    scheduler.add_job(
        shelf_job.__call__,
        trigger=IntervalTrigger(minutes=context.settings.SHELF_HEAT_CHECK_MINUTES),
        id="shelf_heat",
        replace_existing=True,
    )
