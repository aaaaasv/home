from src.bot.handlers.system.jobs import SHELF_HEAT_KIND, ShelfHeatJob
from src.bot.services.posted_message_tracker import PostedMessageTracker
from src.infrastructure.db.uow import UnitOfWork
from src.modules.room_climate.domain import RoomClimate
from src.tests.fakes import FixedRoomClimateSensor, RecordingBot, StubForumTopic
from src.tests.integration.base import BaseIntegrationTestCase

CHAT_ID = -1001234567890


class ShelfHeatTestCase(BaseIntegrationTestCase):
    """
    The one sensor that stands where the heat is, and how seldom it is allowed to speak.

    the shelf carries the pi, the router, the media laptop and the ups cells. a card that repeated every quarter
    of an hour would be muted within a day, so the card itself is the memory of what has already been said.
    """

    def uow_factory(self) -> UnitOfWork:
        return UnitOfWork(session_factory=self.session_factory)

    def build_job(self, bot: RecordingBot, temperature: float | None) -> ShelfHeatJob:
        climate = (
            None
            if temperature is None
            else RoomClimate(temperature_celsius=temperature, relative_humidity_percent=30.0)
        )
        return ShelfHeatJob(
            bot=bot,
            chat_id=CHAT_ID,
            tech_topic=StubForumTopic(),
            sensor=FixedRoomClimateSensor(climate),
            posted_message_tracker=PostedMessageTracker(bot=bot, uow_factory=self.uow_factory),
            uow_factory=self.uow_factory,
        )

    async def test_shelf_below_the_warm_threshold_says_nothing(self):
        bot = RecordingBot()

        await self.build_job(bot, 33.0)()

        self.assertEqual(bot.sent, [])

    async def test_shelf_above_forty_posts_one_card_with_a_ping(self):
        bot = RecordingBot()

        await self.build_job(bot, 41.4)()

        self.assertEqual(
            [(message["text"], message["silent"]) for message in bot.sent],
            [
                (
                    "🌡 <b>Серверна полиця 41°</b> — ноутбуку й акумуляторам вже некомфортно. "
                    "Варто прибрати, що гріє поруч, або дати більше повітря.",
                    False,
                )
            ],
        )

    async def test_shelf_staying_warm_does_not_post_a_second_card(self):
        bot = RecordingBot()
        await self.build_job(bot, 41.0)()

        await self.build_job(bot, 42.0)()

        self.assertEqual(len(bot.sent), 1)

    async def test_shelf_climbing_past_forty_five_escalates_to_a_second_card(self):
        bot = RecordingBot()
        await self.build_job(bot, 41.0)()

        await self.build_job(bot, 46.2)()

        self.assertEqual(
            bot.sent[-1]["text"],
            "🔥 <b>Серверна полиця 46°</b> — заряджати літій за такої температури шкідливо. "
            "Варто розвантажити полицю зараз.",
        )

    async def test_shelf_already_hot_does_not_repeat_the_hot_card(self):
        bot = RecordingBot()
        await self.build_job(bot, 46.0)()

        await self.build_job(bot, 47.0)()

        self.assertEqual(len(bot.sent), 1)

    async def test_shelf_cooling_only_to_thirty_eight_keeps_the_card_standing(self):
        bot = RecordingBot()
        await self.build_job(bot, 41.0)()

        await self.build_job(bot, 38.0)()

        async with self.uow as uow:
            standing = await uow.posted_messages.list_by_kind(SHELF_HEAT_KIND)
        self.assertEqual((len(bot.sent), [posted.reference for posted in standing]), (1, ["warm"]))

    async def test_shelf_cooling_clearly_takes_the_card_down_quietly(self):
        bot = RecordingBot()
        await self.build_job(bot, 46.0)()

        await self.build_job(bot, 34.0)()

        async with self.uow as uow:
            standing = await uow.posted_messages.list_by_kind(SHELF_HEAT_KIND)
        self.assertEqual(
            ([(message["text"], message["silent"]) for message in bot.sent[1:]], standing),
            ([("🌡 Серверна полиця охолола — 34°", True)], []),
        )

    async def test_shelf_with_a_silent_sensor_says_nothing_and_keeps_the_card(self):
        bot = RecordingBot()
        await self.build_job(bot, 46.0)()

        await self.build_job(bot, None)()

        async with self.uow as uow:
            standing = await uow.posted_messages.list_by_kind(SHELF_HEAT_KIND)
        self.assertEqual((len(bot.sent), [posted.reference for posted in standing]), (1, ["hot"]))


class ShelfHeatRetentionTestCase(ShelfHeatTestCase):
    """A card deleted by hand must not silence the shelf forever — the next step up posts again."""

    async def test_shelf_whose_card_was_removed_reports_the_same_level_again(self):
        bot = RecordingBot()
        await self.build_job(bot, 41.0)()
        async with self.uow as uow:
            for posted in await uow.posted_messages.list_by_kind(SHELF_HEAT_KIND):
                await uow.posted_messages.delete(posted.id)

        await self.build_job(bot, 41.0)()

        self.assertEqual(len(bot.sent), 2)
