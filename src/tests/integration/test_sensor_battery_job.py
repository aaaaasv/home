from datetime import timedelta

from src.bot.handlers.system.jobs import SENSOR_BATTERY_KIND, SensorBatteryJob
from src.bot.services.posted_message_tracker import PostedMessageTracker
from src.common.config import Settings
from src.infrastructure.db.uow import UnitOfWork
from src.tests.fakes import RecordingBot, StubForumTopic
from src.tests.integration.base import BaseIntegrationTestCase

CHAT_ID = -1000
THREAD_ID = 55
BEDROOM_SENSOR = "temp-bedroom"
KITCHEN_SENSOR = "temp-kitchen"
POT_SENSOR = "soil-probe"


class SensorBatteryJobTestCase(BaseIntegrationTestCase):
    """
    One card per sensor when its cell runs low — about three a year, so each one has to be worth reading.

    the failures that would make it worthless are the mirror images: a card that repeats every hour, a card that
    flaps when a tired cell recovers for a moment, and a card that stays after the cell was replaced.
    """

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.bot = RecordingBot()

    def uow_factory(self) -> UnitOfWork:
        return UnitOfWork(session_factory=self.session_factory)

    def build_job(self, plant_id: int | None = None) -> SensorBatteryJob:
        settings = Settings(
            TELEGRAM_BOT_TOKEN="123:abc",
            SENSOR_ROOMS=f'{{"{BEDROOM_SENSOR}": "спальня", "{KITCHEN_SENSOR}": "кухня"}}',
            PLANT_SOIL_SENSORS=f'{{"{POT_SENSOR}": {plant_id}}}' if plant_id is not None else "",
        )
        return SensorBatteryJob(
            bot=self.bot,
            chat_id=CHAT_ID,
            tech_topic=StubForumTopic(THREAD_ID),
            uow_factory=self.uow_factory,
            household_calendar=self.household_calendar,
            settings=settings,
            posted_message_tracker=PostedMessageTracker(bot=self.bot, uow_factory=self.uow_factory),
        )

    async def record(self, sensor: str, battery: float | None, minutes_ago: int = 1) -> None:
        async with self.uow as uow:
            await uow.sensor_readings.create(
                {
                    "sensor": sensor,
                    "room": None,
                    "measured_at": self.household_calendar.now() - timedelta(minutes=minutes_ago),
                    "temperature_celsius": 21.0,
                    "relative_humidity_percent": 45.0,
                    "soil_moisture_percent": None,
                    "battery_percent": battery,
                }
            )

    async def list_cards(self) -> list[str]:
        async with self.uow as uow:
            return sorted(posted.reference for posted in await uow.posted_messages.list_by_kind(SENSOR_BATTERY_KIND))

    async def test_call_with_a_low_battery_posts_one_card_with_a_ping_in_the_tech_topic(self):
        await self.record(BEDROOM_SENSOR, battery=11)
        job = self.build_job()

        await job()

        self.assertEqual(
            self.bot.sent,
            [
                {
                    "message_id": 500,
                    "chat_id": CHAT_ID,
                    "message_thread_id": THREAD_ID,
                    "text": "🔋 <b>Датчик «спальня»</b> — лишилось 11% батареї. Час поміняти елемент живлення.",
                    "silent": False,
                }
            ],
        )
        self.assertEqual(await self.list_cards(), [BEDROOM_SENSOR])

    async def test_call_twice_with_the_battery_still_low_posts_the_card_only_once(self):
        await self.record(BEDROOM_SENSOR, battery=11)
        job = self.build_job()
        await job()

        await job()

        self.assertEqual(len(self.bot.sent), 1)
        self.assertEqual(self.bot.deleted, [])

    async def test_call_with_healthy_batteries_stays_silent(self):
        await self.record(BEDROOM_SENSOR, battery=87)
        await self.record(KITCHEN_SENSOR, battery=None)
        job = self.build_job()

        await job()

        self.assertEqual(self.bot.sent, [])
        self.assertEqual(await self.list_cards(), [])

    async def test_call_with_a_battery_between_the_two_thresholds_and_no_card_stays_silent(self):
        await self.record(BEDROOM_SENSOR, battery=25)
        job = self.build_job()

        await job()

        self.assertEqual(self.bot.sent, [])

    async def test_call_with_a_carded_battery_that_recovers_a_little_keeps_the_card_and_does_not_repost(self):
        await self.record(BEDROOM_SENSOR, battery=11)
        job = self.build_job()
        await job()
        await self.record(BEDROOM_SENSOR, battery=25, minutes_ago=0)

        await job()

        self.assertEqual(len(self.bot.sent), 1)
        self.assertEqual(self.bot.deleted, [])
        self.assertEqual(await self.list_cards(), [BEDROOM_SENSOR])

    async def test_call_after_the_cell_was_replaced_deletes_the_card(self):
        await self.record(BEDROOM_SENSOR, battery=11)
        job = self.build_job()
        await job()
        await self.record(BEDROOM_SENSOR, battery=100, minutes_ago=0)

        await job()

        self.assertEqual(self.bot.deleted, [500])
        self.assertEqual(await self.list_cards(), [])

    async def test_call_with_two_low_sensors_posts_a_card_for_each(self):
        await self.record(BEDROOM_SENSOR, battery=11)
        await self.record(KITCHEN_SENSOR, battery=17)
        job = self.build_job()

        await job()

        self.assertEqual(await self.list_cards(), [BEDROOM_SENSOR, KITCHEN_SENSOR])
        self.assertEqual(len(self.bot.sent), 2)

    async def test_call_with_a_low_probe_names_it_after_the_plant_it_stands_in(self):
        plant_id = await self.seed_plant(name="Бубик")
        await self.record(POT_SENSOR, battery=9)
        job = self.build_job(plant_id=plant_id)

        await job()

        self.assertEqual(
            [sent["text"] for sent in self.bot.sent],
            ["🔋 <b>Датчик у горщику «Бубик»</b> — лишилось 9% батареї. Час поміняти елемент живлення."],
        )
