from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.bot.handlers.power.outage_schedule_board import OutageScheduleBoard
from src.bot.services.posted_message_tracker import OUTAGE_SCHEDULE_KIND
from src.infrastructure.db.uow import UnitOfWork
from src.modules.power.domain import OutageInterval, OutageOutlook, OutageSchedule, OutageScheduleStatus
from src.tests.fakes import StubForumTopic
from src.tests.integration.base import BaseIntegrationTestCase

CHAT_ID = -1001234567890
KYIV = ZoneInfo("Europe/Kyiv")


class RecordingBoardBot:
    """Records what the board asked Telegram to do."""

    def __init__(self):
        self.sent: list[str] = []
        self.edited: list[tuple[int, str]] = []
        self.deleted: list[int] = []

    async def send_message(self, chat_id, message_thread_id, text, reply_markup, disable_notification):
        self.sent.append(text)

        class Chat:
            id = chat_id

        class Sent:
            chat = Chat()
            message_id = 700 + len(self.sent)

        return Sent()

    async def edit_message_text(self, chat_id, message_id, text, reply_markup):
        self.edited.append((message_id, text))

    async def delete_message(self, chat_id, message_id):
        self.deleted.append(message_id)


class StubScheduleProvider:
    def __init__(self, outlook: OutageOutlook | None = None):
        self.outlook = outlook
        self.fetches = 0

    async def fetch(self) -> OutageOutlook | None:
        self.fetches += 1
        return self.outlook

    async def fetch_today(self) -> OutageSchedule | None:
        raise AssertionError("the board must read both days, not today alone")


def build_schedule(day: date, *intervals: OutageInterval) -> OutageSchedule:
    return OutageSchedule(
        day=day,
        status=OutageScheduleStatus.SCHEDULE_APPLIES,
        off_intervals=intervals,
        updated_on=None,
    )


class OutageScheduleBoardTestCase(BaseIntegrationTestCase):
    def uow_factory(self) -> UnitOfWork:
        return UnitOfWork(session_factory=self.session_factory)

    def build_board(self, bot, provider: StubScheduleProvider) -> OutageScheduleBoard:
        return OutageScheduleBoard(
            bot=bot,
            chat_id=CHAT_ID,
            power_topic=StubForumTopic(),
            uow_factory=self.uow_factory,
            schedule_provider=provider,
            timezone=KYIV,
        )

    async def remembered_message_ids(self) -> list[int]:
        async with self.uow_factory() as uow:
            return [posted.message_id for posted in await uow.posted_messages.list_by_kind(OUTAGE_SCHEDULE_KIND)]

    def tomorrow_only_outlook(self) -> OutageOutlook:
        """An outlook whose only intervals are tomorrow's — ahead of any wall clock the test may run at."""
        today = datetime.now(KYIV).date()
        return OutageOutlook(
            today=build_schedule(today),
            tomorrow=build_schedule(today + timedelta(days=1), OutageInterval(900, 1110)),
        )

    def spent_day_outlook(self) -> OutageOutlook:
        """A day that is already over and nothing published for tomorrow — behind any wall clock."""
        return OutageOutlook(today=build_schedule(date(2026, 1, 2), OutageInterval(0, 210)), tomorrow=None)

    async def test_post_with_tomorrow_planned_shows_both_day_headings(self):
        bot = RecordingBoardBot()

        await self.build_board(bot, StubScheduleProvider(self.tomorrow_only_outlook())).post()

        self.assertEqual(len(bot.sent), 1)
        self.assertIn("<b>Завтра</b>", bot.sent[0])
        self.assertIn("🕯 15:00–18:30", bot.sent[0])
        self.assertEqual(await self.remembered_message_ids(), [701])

    async def test_post_with_a_day_that_has_no_outages_leaves_that_day_out(self):
        bot = RecordingBoardBot()

        await self.build_board(bot, StubScheduleProvider(self.tomorrow_only_outlook())).post()

        self.assertNotIn("<b>Сьогодні</b>", bot.sent[0])

    async def test_post_with_every_interval_spent_and_no_tomorrow_says_nothing(self):
        bot = RecordingBoardBot()

        await self.build_board(bot, StubScheduleProvider(self.spent_day_outlook())).post()

        self.assertEqual(bot.sent, [])
        self.assertEqual(await self.remembered_message_ids(), [])

    async def test_post_with_a_failed_fetch_says_nothing(self):
        bot = RecordingBoardBot()

        await self.build_board(bot, StubScheduleProvider(None)).post()

        self.assertEqual(bot.sent, [])
        self.assertEqual(await self.remembered_message_ids(), [])

    async def test_refresh_with_no_board_yet_returns_false_and_sends_nothing(self):
        bot = RecordingBoardBot()
        provider = StubScheduleProvider(self.tomorrow_only_outlook())

        refreshed = await self.build_board(bot, provider).refresh()

        self.assertFalse(refreshed)
        self.assertEqual(bot.sent, [])
        self.assertEqual(provider.fetches, 0)

    async def test_refresh_with_a_standing_board_edits_it_in_place(self):
        bot = RecordingBoardBot()
        provider = StubScheduleProvider(self.tomorrow_only_outlook())
        board = self.build_board(bot, provider)
        await board.post()

        refreshed = await board.refresh()

        self.assertTrue(refreshed)
        self.assertEqual(len(bot.edited), 1)
        self.assertEqual(bot.edited[0][0], 701)
        self.assertIn("<b>Завтра</b>", bot.edited[0][1])

    async def test_refresh_once_the_day_is_spent_takes_the_board_down(self):
        bot = RecordingBoardBot()
        board = self.build_board(bot, StubScheduleProvider(self.tomorrow_only_outlook()))
        await board.post()

        refreshed = await self.build_board(bot, StubScheduleProvider(self.spent_day_outlook())).refresh()

        self.assertTrue(refreshed)
        self.assertEqual(bot.deleted, [701])
        self.assertEqual(await self.remembered_message_ids(), [])
