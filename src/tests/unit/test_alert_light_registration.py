import unittest

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.bot.handlers.air_alert.jobs import register_jobs
from src.bot.scheduling import SchedulerContext
from src.common.config import Settings
from src.common.household_calendar import HouseholdCalendar
from src.modules.room_climate.services.room_climate_sensor import NullRoomClimateSensor
from src.tests.fakes import ScriptedPriceSource
from src.tests.integration.base import KYIV


class StubAirAlertWatcher:
    async def __call__(self) -> None:
        return None


class AlertLightRegistrationTestCase(unittest.TestCase):
    """
    The clock must drive the very watcher the socket drives — a wiring fact no behaviour test can see.

    the strip goes up on a red alert and comes back out a quarter of an hour later, and that quarter of an
    hour is counted inside the watcher. the scheduler used to build a second watcher out of the same parts:
    it never saw the raise, so it never lowered anything, and the strip instead went out at the next change
    of alert level — an hour and ten, then two hours, on the night of 13/14.10, with nobody able to reach it.
    """

    def build_scheduler(self, watcher, enabled: bool = True) -> AsyncIOScheduler:
        scheduler = AsyncIOScheduler(timezone=KYIV)
        register_jobs(
            scheduler,
            SchedulerContext(
                bot=None,
                settings=Settings(TELEGRAM_BOT_TOKEN="123:abc", ALERT_LIGHT_ENABLED=enabled),
                household_calendar=HouseholdCalendar(timezone=KYIV),
                care_topic=None,
                shopping_topic=None,
                chores_topic=None,
                room_climate_sensor=NullRoomClimateSensor(),
                price_source=ScriptedPriceSource({}),
                air_alert_watcher=watcher,
            ),
        )
        return scheduler

    def test_register_jobs_schedules_the_sweep_on_the_watcher_it_was_given(self):
        watcher = StubAirAlertWatcher()

        scheduler = self.build_scheduler(watcher)

        self.assertIs(scheduler.get_jobs()[0].func.__self__, watcher)

    def test_register_jobs_with_no_watcher_schedules_nothing(self):
        scheduler = self.build_scheduler(None)

        self.assertEqual(scheduler.get_jobs(), [])

    def test_register_jobs_with_the_module_switched_off_schedules_nothing(self):
        scheduler = self.build_scheduler(StubAirAlertWatcher(), enabled=False)

        self.assertEqual(scheduler.get_jobs(), [])
