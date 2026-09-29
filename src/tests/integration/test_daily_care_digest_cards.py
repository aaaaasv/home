import json
from datetime import date, timedelta
from types import SimpleNamespace

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageCaption, EditMessageText
from sqlalchemy import update

from src.bot.handlers.plants.jobs import DailyCareDigestJob
from src.bot.handlers.plants.messages import SOIL_WATERING_DETECTED
from src.bot.handlers.plants.soil import build_watering_recorder
from src.bot.services.posted_message_tracker import CARE_DIGEST_KIND, PostedMessageTracker
from src.common.config import Settings, get_settings
from src.common.constants import CareTaskType
from src.infrastructure.db.models import CareSchedule
from src.infrastructure.db.uow import UnitOfWork
from src.tests.fakes import FrozenHouseholdCalendar, RecordingBot, StubForumTopic
from src.tests.integration.base import FROZEN_NOW, KYIV, BaseIntegrationTestCase

CHAT_ID = -1001234567890
POT_SENSOR = "soil-probe"


class UneditableBot(RecordingBot):
    """A bot whose edits are refused the way telegram refuses a card somebody deleted by hand."""

    async def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        raise TelegramBadRequest(
            method=EditMessageText(chat_id=chat_id, message_id=message_id, text=text),
            message="Bad Request: message to edit not found",
        )


class PhotoAwareBot(RecordingBot):
    """A bot that can also post a photo with a caption and rewrite that caption."""

    def __init__(self) -> None:
        super().__init__()
        self.posted_photos: list[dict] = []
        self.edited_captions: list[dict] = []

    async def send_photo(
        self, chat_id, message_thread_id=None, photo=None, caption=None, reply_markup=None, disable_notification=False
    ):
        message_id = self.next_message_id
        self.next_message_id += 1
        self.posted_photos.append({"message_id": message_id, "photo": photo, "caption": caption})
        return SimpleNamespace(message_id=message_id, chat=SimpleNamespace(id=chat_id))

    async def edit_message_caption(self, chat_id, message_id, caption, reply_markup=None):
        self.edited_captions.append({"message_id": message_id, "caption": caption})


class TextOnlyMessagesBot(PhotoAwareBot):
    """Telegram's answer when a caption edit is aimed at a message that is plain text."""

    async def edit_message_caption(self, chat_id, message_id, caption, reply_markup=None):
        raise TelegramBadRequest(
            method=EditMessageCaption(chat_id=chat_id, message_id=message_id, caption=caption),
            message="Bad Request: there is no caption in the message to edit",
        )


class DailyCareDigestCardsTestCase(BaseIntegrationTestCase):
    """
    One standing card per plant, driven through the job the way consecutive mornings drive it.

    the mornings are one bot and one database with the clock moved a day on, so what the second run does to the
    first run's messages is exactly what the family would see in the topic.
    """

    def uow_factory(self) -> UnitOfWork:
        return UnitOfWork(session_factory=self.session_factory)

    async def seed_due_task(self, plant_id: int, task_type: CareTaskType, next_due_on: date | None = None) -> None:
        await self.seed_care_schedule(
            plant_id=plant_id, task_type=task_type, interval_days=7, next_due_on=next_due_on or self.today
        )

    async def settle_task(self, plant_id: int, task_type: CareTaskType) -> None:
        async with self.uow as uow:
            await uow.session.execute(
                update(CareSchedule)
                .where(CareSchedule.plant_id == plant_id, CareSchedule.task_type == task_type)
                .values(next_due_on=self.today + timedelta(days=30))
            )

    async def run_digest(self, bot: RecordingBot, days_later: int = 0, settings: Settings | None = None) -> None:
        calendar = FrozenHouseholdCalendar(timezone=KYIV, frozen_now=FROZEN_NOW + timedelta(days=days_later))
        await DailyCareDigestJob(
            bot=bot,
            chat_id=CHAT_ID,
            care_topic=StubForumTopic(),
            uow_factory=self.uow_factory,
            household_calendar=calendar,
            settings=settings or get_settings(),
            posted_message_tracker=PostedMessageTracker(bot=bot, uow_factory=self.uow_factory),
        )()

    async def test_send_digest_with_several_tasks_of_one_plant_posts_a_single_card(self):
        plant_id = await self.seed_plant(name="Кактус")
        await self.seed_due_task(plant_id, CareTaskType.WATERING)
        await self.seed_due_task(plant_id, CareTaskType.FERTILIZING)
        await self.seed_due_task(plant_id, CareTaskType.PHOTO)
        bot = RecordingBot()

        await self.run_digest(bot)

        self.assertEqual([message["text"] for message in bot.sent], ["🪴 <b>Кактус</b>\n💧 полив\n🌱 добриво\n📸 фото"])

    async def test_send_digest_with_two_plants_posts_a_card_for_each(self):
        for name in ("Кактус", "Монстера"):
            await self.seed_due_task(await self.seed_plant(name=name), CareTaskType.WATERING)
        bot = RecordingBot()

        await self.run_digest(bot)

        self.assertEqual(
            [message["text"] for message in bot.sent], ["🪴 <b>Кактус</b>\n💧 полив", "🪴 <b>Монстера</b>\n💧 полив"]
        )

    async def test_send_digest_the_next_day_with_nothing_new_edits_the_card_in_place(self):
        plant_id = await self.seed_plant(name="Кактус")
        await self.seed_due_task(plant_id, CareTaskType.WATERING)
        bot = RecordingBot()
        await self.run_digest(bot)

        await self.run_digest(bot, days_later=1)

        self.assertEqual(
            (len(bot.sent), bot.edited, bot.deleted),
            (1, [{"chat_id": CHAT_ID, "message_id": 500, "text": "🔴 <b>Кактус</b>\n💧 полив · 1 день"}], []),
        )

    async def test_send_digest_when_a_new_need_appears_posts_a_new_card_and_deletes_the_old_one(self):
        plant_id = await self.seed_plant(name="Кактус")
        await self.seed_due_task(plant_id, CareTaskType.WATERING)
        bot = RecordingBot()
        await self.run_digest(bot)
        await self.seed_due_task(plant_id, CareTaskType.PHOTO)

        await self.run_digest(bot, days_later=1)

        self.assertEqual(
            ([(message["text"], message["silent"]) for message in bot.sent[1:]], bot.edited, bot.deleted),
            ([("🔴 <b>Кактус</b>\n💧 полив · 1 день\n📸 фото · 1 день", False)], [], [500]),
        )

    async def test_send_digest_when_one_of_two_needs_is_done_edits_the_card_without_a_new_message(self):
        plant_id = await self.seed_plant(name="Кактус")
        await self.seed_due_task(plant_id, CareTaskType.WATERING)
        await self.seed_due_task(plant_id, CareTaskType.PHOTO)
        bot = RecordingBot()
        await self.run_digest(bot)
        await self.settle_task(plant_id, CareTaskType.PHOTO)

        await self.run_digest(bot, days_later=1)

        self.assertEqual(
            (len(bot.sent), [edit["text"] for edit in bot.edited], bot.deleted),
            (1, ["🔴 <b>Кактус</b>\n💧 полив · 1 день"], []),
        )

    async def test_send_digest_when_every_task_is_done_deletes_the_standing_card(self):
        plant_id = await self.seed_plant(name="Кактус")
        await self.seed_due_task(plant_id, CareTaskType.WATERING)
        bot = RecordingBot()
        await self.run_digest(bot)
        await self.settle_task(plant_id, CareTaskType.WATERING)

        await self.run_digest(bot, days_later=1)

        self.assertEqual((len(bot.sent), bot.edited, bot.deleted), (1, [], [500]))

    async def test_send_digest_when_one_plant_is_done_and_another_is_not_deletes_only_the_done_plants_card(self):
        cactus_id = await self.seed_plant(name="Кактус")
        monstera_id = await self.seed_plant(name="Монстера")
        await self.seed_due_task(cactus_id, CareTaskType.WATERING)
        await self.seed_due_task(monstera_id, CareTaskType.WATERING)
        bot = RecordingBot()
        await self.run_digest(bot)
        await self.settle_task(cactus_id, CareTaskType.WATERING)

        await self.run_digest(bot, days_later=1)

        self.assertEqual((len(bot.sent), [edit["message_id"] for edit in bot.edited], bot.deleted), (2, [501], [500]))

    async def test_send_digest_with_a_card_telegram_cannot_edit_posts_it_again_without_a_ping(self):
        plant_id = await self.seed_plant(name="Кактус")
        await self.seed_due_task(plant_id, CareTaskType.WATERING)
        bot = UneditableBot()
        await self.run_digest(bot)

        await self.run_digest(bot, days_later=1)

        self.assertEqual(
            ([(message["text"], message["silent"]) for message in bot.sent[1:]], bot.deleted),
            ([("🔴 <b>Кактус</b>\n💧 полив · 1 день", True)], [500]),
        )

    async def test_send_digest_replaces_a_card_left_by_the_one_card_per_task_format(self):
        plant_id = await self.seed_plant(name="Кактус")
        await self.seed_due_task(plant_id, CareTaskType.WATERING)
        async with self.uow as uow:
            await uow.posted_messages.create(
                {"kind": CARE_DIGEST_KIND, "chat_id": CHAT_ID, "message_id": 400, "reference": "watering:5"}
            )
        bot = RecordingBot()

        await self.run_digest(bot)

        self.assertEqual((len(bot.sent), bot.deleted), (1, [400]))

    async def test_send_digest_remembers_each_card_by_its_plant_and_its_needs(self):
        plant_id = await self.seed_plant(name="Кактус")
        await self.seed_due_task(plant_id, CareTaskType.WATERING)
        await self.seed_due_task(plant_id, CareTaskType.PHOTO)
        bot = RecordingBot()

        await self.run_digest(bot)

        async with self.uow as uow:
            tracked = await uow.posted_messages.list_by_kind(CARE_DIGEST_KIND)
        self.assertEqual([(posted.message_id, posted.reference) for posted in tracked], [(500, f"{plant_id}:65")])

    async def test_send_digest_for_a_plant_with_a_probe_adds_the_pot_reading(self):
        plant_id = await self.seed_plant(name="Містер Біг")
        await self.seed_due_task(plant_id, CareTaskType.WATERING)
        async with self.uow as uow:
            await uow.sensor_readings.create(
                {
                    "sensor": POT_SENSOR,
                    "room": None,
                    "measured_at": FROZEN_NOW - timedelta(minutes=1),
                    "temperature_celsius": 21.3,
                    "soil_moisture_percent": 12.0,
                }
            )
        settings = get_settings().model_copy(update={"PLANT_SOIL_SENSORS": json.dumps({POT_SENSOR: plant_id})})
        bot = RecordingBot()

        await self.run_digest(bot, settings=settings)

        self.assertEqual(
            [message["text"] for message in bot.sent], ["🪴 <b>Містер Біг</b>\n💧 полив\n🌡 у горщику 21° · ґрунт 12%"]
        )

    async def test_send_digest_for_a_plant_with_only_a_room_sensor_leaves_the_sensor_line_out(self):
        plant_id = await self.seed_plant(name="Кактус", room="спальня")
        await self.seed_due_task(plant_id, CareTaskType.WATERING)
        await self.seed_sensor_readings(
            room="спальня", since=FROZEN_NOW - timedelta(hours=1), until=FROZEN_NOW - timedelta(minutes=1)
        )
        bot = RecordingBot()

        await self.run_digest(bot)

        self.assertEqual([message["text"] for message in bot.sent], ["🪴 <b>Кактус</b>\n💧 полив"])

    async def test_send_digest_for_a_plant_with_a_photo_posts_the_card_as_the_photos_caption(self):
        plant_id = await self.seed_plant(name="Кактус")
        await self.seed_plant_photo(plant_id, telegram_file_id="file-cactus")
        await self.seed_due_task(plant_id, CareTaskType.WATERING)
        bot = PhotoAwareBot()

        await self.run_digest(bot)

        self.assertEqual(
            (bot.sent, bot.posted_photos),
            ([], [{"message_id": 500, "photo": "file-cactus", "caption": "🪴 <b>Кактус</b>\n💧 полив"}]),
        )

    async def test_send_digest_the_next_day_with_a_photo_card_rewrites_its_caption(self):
        plant_id = await self.seed_plant(name="Кактус")
        await self.seed_plant_photo(plant_id, telegram_file_id="file-cactus")
        await self.seed_due_task(plant_id, CareTaskType.WATERING)
        bot = PhotoAwareBot()
        await self.run_digest(bot)

        await self.run_digest(bot, days_later=1)

        self.assertEqual(
            (bot.edited, bot.edited_captions, bot.deleted),
            ([], [{"message_id": 500, "caption": "🔴 <b>Кактус</b>\n💧 полив · 1 день"}], []),
        )

    async def test_send_digest_for_a_text_card_whose_plant_has_since_got_a_photo_still_edits_it_in_place(self):
        plant_id = await self.seed_plant(name="Кактус")
        await self.seed_due_task(plant_id, CareTaskType.WATERING)
        bot = TextOnlyMessagesBot()
        await self.run_digest(bot)
        await self.seed_plant_photo(plant_id, telegram_file_id="file-cactus")

        await self.run_digest(bot, days_later=1)

        self.assertEqual((len(bot.sent), [edit["message_id"] for edit in bot.edited], bot.deleted), (1, [500], []))


class SoilWateringOnTheStandingCardTestCase(DailyCareDigestCardsTestCase):
    """
    The probe writes a watering down by itself, and the card asking for that watering has to notice.

    this is the seam between two features built weeks apart: nobody taps anything, so the only thing that can
    settle the card is the recorder. the detection has its own tests and they stub the recorder out, which left
    the half that touches the card with no test at all.
    """

    async def detect_watering(self, bot: RecordingBot, plant_id: int) -> None:
        await build_watering_recorder(
            bot=bot,
            settings=get_settings(),
            care_topic=StubForumTopic(),
            uow_factory=self.uow_factory,
            household_calendar=self.household_calendar,
        )(plant_id)

    async def test_detect_watering_of_a_plant_that_needs_nothing_else_takes_its_card_away(self):
        plant_id = await self.seed_plant(name="Кактус")
        await self.seed_due_task(plant_id, CareTaskType.WATERING)
        bot = RecordingBot()
        await self.run_digest(bot)

        await self.detect_watering(bot, plant_id)

        async with self.uow as uow:
            standing = await uow.posted_messages.list_by_kind(CARE_DIGEST_KIND)
        self.assertEqual((bot.deleted, standing), ([500], []))

    async def test_detect_watering_of_a_plant_that_still_needs_a_photo_leaves_the_photo_on_the_card(self):
        plant_id = await self.seed_plant(name="Кактус")
        await self.seed_due_task(plant_id, CareTaskType.WATERING)
        await self.seed_due_task(plant_id, CareTaskType.PHOTO)
        bot = RecordingBot()
        await self.run_digest(bot)

        await self.detect_watering(bot, plant_id)

        async with self.uow as uow:
            standing = await uow.posted_messages.list_by_kind(CARE_DIGEST_KIND)
        self.assertEqual(
            (bot.edited, bot.deleted, [(posted.message_id, posted.reference) for posted in standing]),
            (
                [{"chat_id": CHAT_ID, "message_id": 500, "text": "🪴 <b>Кактус</b>\n📸 фото"}],
                [],
                [(500, f"{plant_id}:64")],
            ),
        )

    async def test_detect_watering_writes_the_care_down_as_the_probe_and_announces_it(self):
        plant_id = await self.seed_plant(name="Кактус")
        await self.seed_due_task(plant_id, CareTaskType.WATERING)
        bot = RecordingBot()
        await self.run_digest(bot)

        await self.detect_watering(bot, plant_id)

        events = await self.list_care_events(plant_id)
        self.assertEqual(
            (
                [(event.task_type, event.performed_by_display_name) for event in events],
                [message["text"].splitlines()[0] for message in bot.sent[1:]],
            ),
            ([(CareTaskType.WATERING, get_settings().PLANT_SOIL_ACTOR_NAME)], [SOIL_WATERING_DETECTED]),
        )

    async def test_detect_watering_minutes_after_somebody_recorded_it_leaves_the_card_alone(self):
        plant_id = await self.seed_plant(name="Кактус")
        await self.seed_due_task(plant_id, CareTaskType.WATERING)
        await self.seed_care_event(
            plant_id, task_type=CareTaskType.WATERING, performed_at=FROZEN_NOW - timedelta(minutes=10)
        )
        bot = RecordingBot()
        await self.run_digest(bot)

        await self.detect_watering(bot, plant_id)

        self.assertEqual((len(bot.sent), bot.edited, bot.deleted), (1, [], []))
