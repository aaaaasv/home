from datetime import date, datetime, timedelta, timezone

from src.bot.handlers.chores.jobs import ChoreDeadlineJob
from src.bot.services.posted_message_tracker import CHORE_DEADLINE_KIND, PostedMessageTracker
from src.common.config import Settings
from src.common.domain import Actor
from src.infrastructure.db.uow import UnitOfWork
from src.modules.chores.commands import AddChoreCommand, SetChoreDeadlineCommand
from src.modules.chores.use_cases.add_chore import AddChoreUseCase
from src.modules.chores.use_cases.set_chore_deadline import SetChoreDeadlineUseCase
from src.tests.fakes import FrozenHouseholdCalendar, RecordingBot, StubForumTopic
from src.tests.integration.base import KYIV, BaseIntegrationTestCase

BOHDAN = Actor(telegram_user_id=1, display_name="Богдан")
TODAY = date(2026, 7, 12)
CHAT_ID = -1000
THREAD_ID = 100


class ChoreDeadlineJobTestCase(BaseIntegrationTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.bot = RecordingBot()
        self.settings = Settings(TELEGRAM_BOT_TOKEN="123:abc")

    def uow_factory(self) -> UnitOfWork:
        return UnitOfWork(session_factory=self.session_factory)

    def build_job(self, today: date) -> ChoreDeadlineJob:
        frozen_now = datetime(today.year, today.month, today.day, 9, 0, tzinfo=timezone.utc)
        return ChoreDeadlineJob(
            bot=self.bot,
            chat_id=CHAT_ID,
            chores_topic=StubForumTopic(THREAD_ID),
            uow_factory=self.uow_factory,
            household_calendar=FrozenHouseholdCalendar(timezone=KYIV, frozen_now=frozen_now),
            settings=self.settings,
            posted_message_tracker=PostedMessageTracker(bot=self.bot, uow_factory=self.uow_factory),
        )

    async def add_chore(self, name: str, due_on: date | None = None) -> int:
        chores = await AddChoreUseCase(uow=self.uow, actor=BOHDAN)(AddChoreCommand(name=name, due_on=due_on))
        return chores.open_chores[0].id

    async def list_cards(self) -> list:
        async with self.uow as uow:
            return await uow.posted_messages.list_by_kind(CHORE_DEADLINE_KIND)

    async def test_a_chore_entering_the_window_posts_a_card_with_a_ping(self):
        chore_id = await self.add_chore("негативи", due_on=TODAY + timedelta(days=1))

        await self.build_job(TODAY)()

        self.assertEqual(self.bot.edited, [])
        self.assertEqual(self.bot.deleted, [])
        self.assertEqual(len(self.bot.sent), 1)
        self.assertEqual(self.bot.sent[0]["text"], "📅 <b>негативи</b> — завтра")
        self.assertEqual(self.bot.sent[0]["silent"], False)
        self.assertEqual(self.bot.sent[0]["message_thread_id"], THREAD_ID)
        cards = await self.list_cards()
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].reference, str(chore_id))

    async def test_an_assigned_chore_card_mentions_the_person(self):
        await AddChoreUseCase(uow=self.uow, actor=BOHDAN)(
            AddChoreCommand(
                name="посилка",
                due_on=TODAY + timedelta(days=1),
                assignee_telegram_user_id=555,
                assignee_display_name="Марта",
            )
        )

        await self.build_job(TODAY)()

        self.assertIn('<a href="tg://user?id=555">Марта</a>', self.bot.sent[0]["text"])

    async def test_a_far_off_or_undated_chore_is_never_carded(self):
        await self.add_chore("далеко", due_on=TODAY + timedelta(days=10))
        await self.add_chore("колись")

        await self.build_job(TODAY)()

        self.assertEqual(self.bot.sent, [])
        self.assertEqual(await self.list_cards(), [])

    async def test_the_next_day_rewrites_the_card_in_place_without_a_new_ping(self):
        await self.add_chore("негативи", due_on=TODAY + timedelta(days=1))
        await self.build_job(TODAY)()
        card_message_id = self.bot.sent[0]["message_id"]

        await self.build_job(TODAY + timedelta(days=1))()

        self.assertEqual(len(self.bot.sent), 1)
        self.assertEqual(self.bot.deleted, [])
        self.assertEqual(len(self.bot.edited), 1)
        self.assertEqual(self.bot.edited[0]["message_id"], card_message_id)
        self.assertEqual(self.bot.edited[0]["text"], "🔴 <b>негативи</b> — сьогодні")
        cards = await self.list_cards()
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].message_id, card_message_id)

    async def test_a_chore_pushed_out_of_the_window_has_its_card_deleted(self):
        chore_id = await self.add_chore("негативи", due_on=TODAY + timedelta(days=1))
        await self.build_job(TODAY)()
        card_message_id = self.bot.sent[0]["message_id"]
        await SetChoreDeadlineUseCase(uow=self.uow)(
            SetChoreDeadlineCommand(chore_id=chore_id, due_on=TODAY + timedelta(days=30))
        )

        await self.build_job(TODAY)()

        self.assertEqual(self.bot.deleted, [card_message_id])
        self.assertEqual(len(self.bot.sent), 1)
        self.assertEqual(await self.list_cards(), [])
