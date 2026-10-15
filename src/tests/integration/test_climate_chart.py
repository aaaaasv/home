import json
import unittest
from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.bot.handlers.weather.chart import find_chart_font
from src.bot.handlers.weather.jobs import ClimateChartJob, register_jobs
from src.bot.scheduling import SchedulerContext
from src.bot.services.posted_message_tracker import CLIMATE_CHART_KIND
from src.common.config import Settings
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.room_climate.services.room_climate_sensor import NullRoomClimateSensor
from src.modules.weather.domain import ClimateDay, ClimateHistory
from src.tests.fakes import ScriptedPriceSource, StubForumTopic
from src.tests.integration.base import KYIV, BaseIntegrationTestCase
from src.tests.integration.test_climate_history import ROOMS, ClimateDaysSeeding

CHAT_ID = -1001234567890
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def build_history(days: int = 30, indoor_from: int = 0) -> ClimateHistory:
    first = date(2026, 9, 15)
    outdoor = tuple(
        ClimateDay(
            day=first + timedelta(days=position),
            minimum_celsius=6.0 + position % 4,
            maximum_celsius=14.0 + position % 5,
            average_celsius=10.0 + position % 4,
            average_humidity_percent=70.0 + position % 10,
        )
        for position in range(days)
    )
    indoor = tuple(
        ClimateDay(
            day=first + timedelta(days=position),
            minimum_celsius=22.0,
            maximum_celsius=25.0 - position % 2,
            average_celsius=23.5,
            average_humidity_percent=45.0,
        )
        for position in range(indoor_from, days)
    )
    return ClimateHistory(indoor=indoor, outdoor=outdoor)


class RecordingPhotoBot:
    def __init__(self):
        self.photos: list[dict] = []
        self.deleted: list[int] = []
        self.next_message_id = 600

    async def send_photo(self, chat_id, message_thread_id, photo, disable_notification):
        self.next_message_id += 1
        self.photos.append(
            {
                "message_id": self.next_message_id,
                "thread": message_thread_id,
                "bytes": photo.data,
                "silent": disable_notification,
            }
        )

        class Sent:
            message_id = self.next_message_id

            class chat:
                id = chat_id

        return Sent()

    async def delete_message(self, chat_id, message_id):
        self.deleted.append(message_id)


class ClimateChartJobTestCase(ClimateDaysSeeding, BaseIntegrationTestCase):
    """One picture a morning in the climate topic, silent, and only the newest one standing."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.bot = RecordingPhotoBot()
        self.fonts = find_chart_font()
        if self.fonts is None:
            self.skipTest("no font on this machine; the image needs fonts-dejavu-core")

    def uow_factory(self) -> UnitOfWork:
        return UnitOfWork(session_factory=self.session_factory)

    def build_job(self) -> ClimateChartJob:
        return ClimateChartJob(
            bot=self.bot,
            chat_id=CHAT_ID,
            weather_topic=StubForumTopic(thread_id=46),
            uow_factory=self.uow_factory,
            household_calendar=self.household_calendar,
            fonts=self.fonts,
            rooms=ROOMS,
            days=30,
        )

    async def seed_a_fortnight(self) -> None:
        for position in range(1, 15):
            day = self.today - timedelta(days=position)
            await self.seed_outdoor_day(day, low=5.0 + position % 3, high=12.0 + position % 4)
            await self.seed_room_day("спальня", day, low=22.0, high=24.0)
            await self.seed_room_day("ванна", day, low=23.0, high=25.0)

    async def test_call_with_a_fortnight_behind_it_posts_one_silent_photo_in_the_climate_topic(self):
        await self.seed_a_fortnight()

        await self.build_job()()

        self.assertEqual(
            [(photo["thread"], photo["silent"], photo["bytes"][:8]) for photo in self.bot.photos],
            [(46, True, PNG_MAGIC)],
        )

    async def test_call_on_the_next_morning_takes_yesterdays_picture_down(self):
        """It is the same picture redrawn, not a record of anything, so two of them is just clutter."""
        await self.seed_a_fortnight()
        await self.build_job()()

        await self.build_job()()

        self.assertEqual(self.bot.deleted, [601])
        async with self.uow_factory() as uow:
            standing = await uow.posted_messages.list_by_kind(CLIMATE_CHART_KIND)
        self.assertEqual([posted.message_id for posted in standing], [602])

    async def test_call_with_nothing_recorded_yet_posts_nothing(self):
        await self.build_job()()

        self.assertEqual(self.bot.photos, [])


class ClimateChartRegistrationTestCase(unittest.TestCase):
    """The chart is drawn only where there is a font, so registration asks before scheduling anything."""

    def build_scheduler(self, enabled: bool = True, rooms: bool = True) -> AsyncIOScheduler:
        scheduler = AsyncIOScheduler(timezone=KYIV)
        register_jobs(
            scheduler,
            SchedulerContext(
                bot=None,
                settings=Settings(
                    TELEGRAM_BOT_TOKEN="123:abc",
                    WEATHER_CHART_ENABLED=enabled,
                    SENSOR_ROOMS=json.dumps({"temp-bedroom": "спальня"}) if rooms else "",
                ),
                household_calendar=HouseholdCalendar(timezone=KYIV),
                care_topic=None,
                shopping_topic=None,
                chores_topic=None,
                room_climate_sensor=NullRoomClimateSensor(),
                price_source=ScriptedPriceSource({}),
                weather_topic=StubForumTopic(thread_id=46),
            ),
        )
        return scheduler

    def test_register_jobs_with_a_font_and_a_room_map_schedules_the_chart(self):
        if find_chart_font() is None:
            self.skipTest("no font on this machine; the image needs fonts-dejavu-core")

        scheduler = self.build_scheduler()

        self.assertEqual([job.id for job in scheduler.get_jobs()], ["climate_chart"])

    def test_register_jobs_with_the_chart_switched_off_schedules_nothing(self):
        scheduler = self.build_scheduler(enabled=False)

        self.assertEqual(scheduler.get_jobs(), [])

    def test_register_jobs_without_a_room_to_draw_schedules_nothing(self):
        scheduler = self.build_scheduler(rooms=False)

        self.assertEqual(scheduler.get_jobs(), [])
