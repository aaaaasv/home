from datetime import datetime, timedelta, timezone

from src.bot.handlers.plants.jobs import RoomClimateJob
from src.bot.services.posted_message_tracker import PLANT_DISCOMFORT_KIND, PostedMessageTracker
from src.common.config import Settings
from src.common.constants import ClimateDimension, ClimateStatus
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.room_climate.domain import RoomClimate
from src.tests.fakes import FixedRoomClimateSensor, RecordingBot, StubForumTopic
from src.tests.integration.base import BaseIntegrationTestCase

ALERT_WINDOW_HOURS = 24
CHAT_ID = -1000
THREAD_ID = 100


class RoomClimateJobTestCase(BaseIntegrationTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        # the use case stamps its own reading with the real clock, so windows are seeded against it
        self.now = datetime.now(timezone.utc)
        self.bot = RecordingBot()
        self.settings = Settings(TELEGRAM_BOT_TOKEN="123:abc")

    def uow_factory(self) -> UnitOfWork:
        return UnitOfWork(session_factory=self.session_factory)

    def build_job(self, temperature: float, humidity: float) -> RoomClimateJob:
        return RoomClimateJob(
            bot=self.bot,
            chat_id=CHAT_ID,
            care_topic=StubForumTopic(THREAD_ID),
            uow_factory=self.uow_factory,
            sensor=FixedRoomClimateSensor(
                RoomClimate(temperature_celsius=temperature, relative_humidity_percent=humidity)
            ),
            settings=self.settings,
            posted_message_tracker=PostedMessageTracker(bot=self.bot, uow_factory=self.uow_factory),
            household_calendar=HouseholdCalendar(timezone=self.settings.timezone),
        )

    async def seed_window(self, temperature: float, humidity: float, until: datetime | None = None) -> None:
        await self.seed_room_climate_readings(
            humidity_percent=humidity,
            temperature_celsius=temperature,
            since=self.now - timedelta(hours=ALERT_WINDOW_HOURS),
            until=until or self.now - timedelta(minutes=1),
        )

    async def seed_discomfort_card(self, plant_id: int, message_id: int, created_at: datetime | None = None) -> None:
        card = {
            "kind": PLANT_DISCOMFORT_KIND,
            "chat_id": CHAT_ID,
            "message_id": message_id,
            "reference": str(plant_id),
        }
        if created_at is not None:
            card["created_at"] = created_at
        async with self.uow as uow:
            await uow.posted_messages.create(card)

    async def list_discomfort_cards(self) -> list:
        async with self.uow as uow:
            return await uow.posted_messages.list_by_kind(PLANT_DISCOMFORT_KIND)

    async def test_room_climate_job_a_plant_becoming_uncomfortable_posts_a_card_and_remembers_it(self):
        plant_id = await self.seed_plant(
            name="Кактус", ideal_humidity_min_percent=50.0, ideal_humidity_max_percent=70.0
        )
        await self.seed_window(temperature=22.0, humidity=32.0)

        await self.build_job(temperature=22.0, humidity=32.0)()

        self.assertEqual(self.bot.edited, [])
        self.assertEqual(self.bot.deleted, [])
        self.assertEqual(len(self.bot.sent), 1)
        self.assertEqual(self.bot.sent[0]["text"], "💧 <b>Кактус</b> — сухо: 32%, треба 50–70%")
        self.assertEqual(self.bot.sent[0]["silent"], False)
        self.assertEqual(self.bot.sent[0]["message_thread_id"], THREAD_ID)
        cards = await self.list_discomfort_cards()
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].reference, str(plant_id))
        self.assertEqual(cards[0].message_id, self.bot.sent[0]["message_id"])

    async def test_room_climate_job_a_plant_recovering_deletes_the_card_and_posts_comfortable(self):
        await self.seed_plant(name="Кактус", ideal_humidity_min_percent=50.0, ideal_humidity_max_percent=70.0)
        await self.seed_window(temperature=22.0, humidity=32.0)
        await self.build_job(temperature=22.0, humidity=32.0)()
        card_message_id = self.bot.sent[0]["message_id"]
        await self.seed_window(temperature=22.0, humidity=60.0, until=self.now)

        await self.build_job(temperature=22.0, humidity=60.0)()

        self.assertEqual(self.bot.deleted, [card_message_id])
        self.assertEqual(len(self.bot.sent), 2)
        self.assertEqual(self.bot.sent[1]["text"], "✅ <b>Кактус</b> — знову комфортно")
        self.assertEqual(self.bot.sent[1]["silent"], True)
        self.assertEqual(await self.list_discomfort_cards(), [])

    async def test_room_climate_job_a_plant_gaining_a_problem_edits_the_card_in_place_silently(self):
        plant_id = await self.seed_plant(
            name="Кактус",
            ideal_temperature_min_celsius=18.0,
            ideal_temperature_max_celsius=27.0,
            ideal_humidity_min_percent=50.0,
            ideal_humidity_max_percent=70.0,
        )
        await self.seed_plant_climate_alert(
            plant_id, ClimateDimension.TEMPERATURE, ClimateStatus.TOO_HIGH, 30.0, self.now - timedelta(hours=1)
        )
        await self.seed_discomfort_card(plant_id, message_id=500)
        await self.seed_window(temperature=30.0, humidity=30.0)

        await self.build_job(temperature=30.0, humidity=30.0)()

        self.assertEqual(self.bot.sent, [])
        self.assertEqual(self.bot.deleted, [])
        self.assertEqual(len(self.bot.edited), 1)
        self.assertEqual(self.bot.edited[0]["message_id"], 500)
        self.assertEqual(
            self.bot.edited[0]["text"],
            "🔥 <b>Кактус</b> — жарко: 30°, треба 18–27°\n💧 <b>Кактус</b> — сухо: 30%, треба 50–70%",
        )
        cards = await self.list_discomfort_cards()
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].message_id, 500)

    async def test_refresh_discomfort_cards_reposts_a_lost_card_silently(self):
        plant_id = await self.seed_plant(
            name="Кактус", ideal_humidity_min_percent=45.0, ideal_humidity_max_percent=90.0
        )
        await self.seed_plant_climate_alert(
            plant_id, ClimateDimension.HUMIDITY, ClimateStatus.TOO_LOW, 44.0, self.now - timedelta(hours=2)
        )
        await self.seed_window(temperature=25.0, humidity=40.0)

        await self.build_job(temperature=25.0, humidity=40.0).refresh_discomfort_cards()

        self.assertEqual(self.bot.edited, [])
        self.assertEqual(len(self.bot.sent), 1)
        self.assertEqual(self.bot.sent[0]["text"], "💧 <b>Кактус</b> — сухо: 40%, треба 45–90%")
        self.assertEqual(self.bot.sent[0]["silent"], True)
        self.assertEqual(self.bot.sent[0]["message_thread_id"], THREAD_ID)
        cards = await self.list_discomfort_cards()
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].reference, str(plant_id))
        self.assertEqual(cards[0].message_id, self.bot.sent[0]["message_id"])

    async def test_refresh_discomfort_cards_reposts_a_card_from_a_previous_day_to_the_bottom(self):
        plant_id = await self.seed_plant(
            name="Кактус", ideal_humidity_min_percent=45.0, ideal_humidity_max_percent=90.0
        )
        await self.seed_plant_climate_alert(
            plant_id, ClimateDimension.HUMIDITY, ClimateStatus.TOO_LOW, 44.0, self.now - timedelta(hours=2)
        )
        await self.seed_discomfort_card(plant_id, message_id=700, created_at=self.now - timedelta(days=1))
        await self.seed_window(temperature=25.0, humidity=40.0)

        await self.build_job(temperature=25.0, humidity=40.0).refresh_discomfort_cards()

        self.assertEqual(self.bot.deleted, [700])
        self.assertEqual(len(self.bot.sent), 1)
        self.assertEqual(self.bot.sent[0]["silent"], True)
        cards = await self.list_discomfort_cards()
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].message_id, self.bot.sent[0]["message_id"])
        self.assertNotEqual(cards[0].message_id, 700)

    async def test_refresh_discomfort_cards_leaves_a_card_already_posted_today_in_place(self):
        plant_id = await self.seed_plant(
            name="Кактус", ideal_humidity_min_percent=45.0, ideal_humidity_max_percent=90.0
        )
        await self.seed_plant_climate_alert(
            plant_id, ClimateDimension.HUMIDITY, ClimateStatus.TOO_LOW, 44.0, self.now - timedelta(hours=2)
        )
        await self.seed_discomfort_card(plant_id, message_id=900, created_at=self.now)
        await self.seed_window(temperature=25.0, humidity=40.0)

        await self.build_job(temperature=25.0, humidity=40.0).refresh_discomfort_cards()

        self.assertEqual(self.bot.sent, [])
        self.assertEqual(self.bot.deleted, [])
        cards = await self.list_discomfort_cards()
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].message_id, 900)

    async def test_refresh_discomfort_cards_cleans_up_a_card_for_a_recovered_plant(self):
        plant_id = await self.seed_plant(
            name="Кактус", ideal_humidity_min_percent=45.0, ideal_humidity_max_percent=90.0
        )
        await self.seed_plant_climate_alert(
            plant_id, ClimateDimension.HUMIDITY, ClimateStatus.OK, 60.0, self.now - timedelta(hours=2)
        )
        await self.seed_discomfort_card(plant_id, message_id=800)
        await self.seed_window(temperature=25.0, humidity=60.0)

        await self.build_job(temperature=25.0, humidity=60.0).refresh_discomfort_cards()

        self.assertEqual(self.bot.deleted, [800])
        self.assertEqual(self.bot.sent, [])
        self.assertEqual(await self.list_discomfort_cards(), [])

    async def test_refresh_discomfort_cards_leaves_a_comfortable_plant_alone(self):
        await self.seed_plant(name="Пеперомія", ideal_humidity_min_percent=30.0, ideal_humidity_max_percent=90.0)
        await self.seed_window(temperature=25.0, humidity=46.0)

        await self.build_job(temperature=25.0, humidity=46.0).refresh_discomfort_cards()

        self.assertEqual(self.bot.sent, [])
        self.assertEqual(await self.list_discomfort_cards(), [])
