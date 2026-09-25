import asyncio
import json
import unittest

from src.bot.handlers.weather.board import WeatherDigestBoard
from src.bot.reminders import build_scheduler
from src.bot.scheduling import SchedulerContext
from src.common.config import Settings
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.room_climate.services.room_climate_sensor import NullRoomClimateSensor
from src.modules.weather.services.weather_provider import NullWeatherProvider
from src.tests.fakes import RecordingPrintQueue, ScriptedPriceSource
from src.tests.integration.base import KYIV


class SchedulerJobsAreAwaitableTestCase(unittest.TestCase):
    def build_scheduler(
        self,
        climate_enabled: bool = False,
        weather_enabled: bool = False,
        newspaper_enabled: bool = False,
        rooms_mapped: bool = False,
    ):
        settings = Settings(
            TELEGRAM_BOT_TOKEN="123:abc",
            CLIMATE_SENSOR_ENABLED=climate_enabled,
            WEATHER_DIGEST_ENABLED=weather_enabled,
            NEWSPAPER_ENABLED=newspaper_enabled,
            SENSOR_ROOMS=json.dumps({"temp-bedroom": "спальня"}) if rooms_mapped else "",
        )
        weather_digest_board = None
        if weather_enabled:
            weather_digest_board = WeatherDigestBoard(
                bot=None,
                chat_id=0,
                weather_topic=object(),
                uow_factory=UnitOfWork,
                weather_provider=NullWeatherProvider(),
                timezone=KYIV,
            )
        return build_scheduler(
            SchedulerContext(
                bot=None,
                settings=settings,
                household_calendar=HouseholdCalendar(timezone=KYIV),
                care_topic=None,
                shopping_topic=None,
                chores_topic=None,
                room_climate_sensor=NullRoomClimateSensor(),
                price_source=ScriptedPriceSource({}),
                weather_topic=object() if weather_enabled else None,
                weather_digest_board=weather_digest_board,
                newspaper_print_queue=RecordingPrintQueue() if newspaper_enabled else None,
            )
        )

    def test_every_scheduled_job_is_a_coroutine_function(self):
        # apscheduler silently drops a job it does not see as a coroutine function, so the whole feature dies quietly
        scheduler = self.build_scheduler(climate_enabled=True, weather_enabled=True, rooms_mapped=True)

        job_functions = [job.func for job in scheduler.get_jobs()]

        self.assertEqual(len(job_functions), 9)
        self.assertTrue(all(asyncio.iscoroutinefunction(function) for function in job_functions))

    def test_plant_comfort_is_scheduled_by_the_room_map_rather_than_by_the_wired_sensor(self):
        scheduler = self.build_scheduler(climate_enabled=False, rooms_mapped=True)

        job_ids = sorted(job.id for job in scheduler.get_jobs())

        self.assertEqual(
            job_ids,
            [
                "chore_deadlines",
                "daily_care_digest",
                "fold_sensor_days",
                "plant_comfort",
                "plant_discomfort_refresh",
                "price_watch",
            ],
        )

    def test_the_wired_sensor_alone_records_its_series_and_judges_no_plant(self):
        scheduler = self.build_scheduler(climate_enabled=True, rooms_mapped=False)

        job_ids = sorted(job.id for job in scheduler.get_jobs())

        self.assertEqual(job_ids, ["chore_deadlines", "daily_care_digest", "price_watch", "room_climate"])

    def test_the_digest_and_price_watch_jobs_are_scheduled_even_without_the_climate_sensor(self):
        scheduler = self.build_scheduler(climate_enabled=False, weather_enabled=False)

        job_ids = sorted(job.id for job in scheduler.get_jobs())

        self.assertEqual(job_ids, ["chore_deadlines", "daily_care_digest", "price_watch"])

    def test_the_weather_digest_and_refresh_jobs_are_scheduled_only_when_enabled(self):
        scheduler = self.build_scheduler(weather_enabled=True)

        job_ids = sorted(job.id for job in scheduler.get_jobs())

        self.assertEqual(
            job_ids, ["chore_deadlines", "daily_care_digest", "price_watch", "weather_digest", "weather_refresh"]
        )

    def test_the_weekly_newspaper_job_is_scheduled_only_when_enabled_with_a_print_queue(self):
        scheduler = self.build_scheduler(newspaper_enabled=True)

        job_ids = sorted(job.id for job in scheduler.get_jobs())

        self.assertEqual(job_ids, ["chore_deadlines", "daily_care_digest", "price_watch", "weekly_newspaper"])
