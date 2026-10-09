from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from src.bot.handlers.power.jobs import YasnoScheduleJob
from src.bot.services.posted_message_tracker import OUTAGE_EMERGENCY_KIND
from src.infrastructure.db.uow import UnitOfWork
from src.modules.power.domain import OutageInterval, OutageOutlook, OutageSchedule, OutageScheduleStatus
from src.tests.fakes import StubForumTopic
from src.tests.integration.base import BaseIntegrationTestCase

CHAT_ID = -1001234567890
KYIV = ZoneInfo("Europe/Kyiv")


class RecordingBot:
    def __init__(self):
        self.sent: list[str] = []

    async def send_message(self, chat_id, message_thread_id, text, **options):
        self.sent.append(text)

        class Chat:
            id = chat_id

        class Sent:
            chat = Chat()
            message_id = 800 + len(self.sent)

        return Sent()

    async def edit_message_text(self, **options):
        return None

    async def delete_message(self, chat_id, message_id):
        return None


class StubProvider:
    def __init__(self, outlook):
        self.outlook = outlook

    async def fetch(self):
        return self.outlook


class StubBoard:
    """Records how the board was drawn: silently refreshed in place, or reposted with a ping."""

    def __init__(self):
        self.refreshes = 0
        self.notified_posts = 0

    async def refresh(self, outlook=None) -> bool:
        self.refreshes += 1
        return True

    async def post(self, outlook=None, notify: bool = False):
        if notify:
            self.notified_posts += 1

        class Chat:
            id = CHAT_ID

        class Posted:
            chat = Chat()
            message_id = 900

        return Posted()


def _minute_of_day_in(minutes_from_now: int) -> int:
    now = datetime.now(KYIV)
    return now.hour * 60 + now.minute + minutes_from_now


def build_outlook(status: OutageScheduleStatus, day: date) -> OutageOutlook:
    return OutageOutlook(today=OutageSchedule(day=day, status=status, off_intervals=(), updated_on=None), tomorrow=None)


class EmergencyAnnouncementTestCase(BaseIntegrationTestCase):
    """
    The group going onto emergency shutdowns reposts the board with a ping — once, until the regime comes back off.

    it used to send a separate alert sentence as well, which said what the board's own banner said a line lower:
    two messages, one regime. and it was keyed on the calendar day, so a spell lasting past midnight announced
    itself again at 00:06 — a notification, at night, repeating what had been said that morning.
    """

    def uow_factory(self) -> UnitOfWork:
        return UnitOfWork(session_factory=self.session_factory)

    def build_job(self, outlook) -> YasnoScheduleJob:
        return YasnoScheduleJob(
            bot=self.bot,
            chat_id=CHAT_ID,
            power_topic=StubForumTopic(),
            uow_factory=self.uow_factory,
            schedule_provider=StubProvider(outlook),
            outage_schedule_board=self.board,
            settings=SimpleNamespace(YASNO_PRE_OUTAGE_LEAD_MINUTES=30),
            timezone=KYIV,
        )

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.bot = RecordingBot()
        self.board = StubBoard()
        self.today = datetime.now(KYIV).date()
        self.tomorrow = date.fromordinal(self.today.toordinal() + 1)

    async def remembered(self) -> int:
        async with self.uow_factory() as uow:
            return len(await uow.posted_messages.list_by_kind(OUTAGE_EMERGENCY_KIND))

    async def test_the_group_going_onto_emergency_shutdowns_reposts_the_board_with_a_ping(self):
        await self.build_job(build_outlook(OutageScheduleStatus.EMERGENCY_SHUTDOWNS, self.today))()

        self.assertEqual(self.board.notified_posts, 1)
        self.assertEqual(await self.remembered(), 1)

    async def test_the_group_going_onto_emergency_shutdowns_sends_no_second_message(self):
        """The alert sentence and the board's banner carried the same fact a minute apart."""
        await self.build_job(build_outlook(OutageScheduleStatus.EMERGENCY_SHUTDOWNS, self.today))()

        self.assertEqual(self.bot.sent, [])

    async def test_the_announcing_tick_does_not_also_refresh_the_board_it_just_reposted(self):
        await self.build_job(build_outlook(OutageScheduleStatus.EMERGENCY_SHUTDOWNS, self.today))()

        self.assertEqual(self.board.refreshes, 0)

    async def test_the_same_spell_polled_again_refreshes_the_board_without_a_ping(self):
        job = self.build_job(build_outlook(OutageScheduleStatus.EMERGENCY_SHUTDOWNS, self.today))
        await job()

        await job()

        self.assertEqual((self.board.notified_posts, self.board.refreshes), (1, 1))

    async def test_a_spell_that_lasts_past_midnight_is_not_announced_again(self):
        """The 00:06 ping: the day rolled over, the regime did not."""
        await self.build_job(build_outlook(OutageScheduleStatus.EMERGENCY_SHUTDOWNS, self.today))()

        await self.build_job(build_outlook(OutageScheduleStatus.EMERGENCY_SHUTDOWNS, self.tomorrow))()

        self.assertEqual(self.board.notified_posts, 1)

    async def test_an_ordinary_day_announces_nothing_and_refreshes_in_place(self):
        await self.build_job(build_outlook(OutageScheduleStatus.SCHEDULE_APPLIES, self.today))()

        self.assertEqual((self.board.notified_posts, self.board.refreshes), (0, 1))
        self.assertEqual(await self.remembered(), 0)

    async def test_a_new_spell_after_the_regime_lifted_is_announced_again(self):
        await self.build_job(build_outlook(OutageScheduleStatus.EMERGENCY_SHUTDOWNS, self.today))()
        await self.build_job(build_outlook(OutageScheduleStatus.SCHEDULE_APPLIES, self.today))()

        await self.build_job(build_outlook(OutageScheduleStatus.EMERGENCY_SHUTDOWNS, self.today))()

        self.assertEqual(self.board.notified_posts, 2)

    def build_outlook_with_an_outage_due_soon(self, status: OutageScheduleStatus) -> OutageOutlook:
        """An hour starting twenty minutes from now, which is inside the thirty-minute heads-up window."""
        starting_soon = OutageInterval(start_minute=_minute_of_day_in(20), end_minute=_minute_of_day_in(200))
        return OutageOutlook(
            today=OutageSchedule(day=self.today, status=status, off_intervals=(starting_soon,), updated_on=None),
            tomorrow=None,
        )

    async def test_an_outage_due_soon_under_an_applying_schedule_is_pinged(self):
        await self.build_job(self.build_outlook_with_an_outage_due_soon(OutageScheduleStatus.SCHEDULE_APPLIES))()

        self.assertEqual(len(self.bot.sent), 1)

    async def test_the_hours_shown_during_emergency_shutdowns_earn_no_pre_outage_ping(self):
        """
        They are the operator's plan, which the operator itself says is not in force in this regime.

        a heads-up for one of them would be wrong about as often as it was right, and that is the surest way
        to get the topic muted. the pair with the test above is the point: the same hour, pinged under one
        regime and silent under the other.
        """
        outlook = self.build_outlook_with_an_outage_due_soon(OutageScheduleStatus.EMERGENCY_SHUTDOWNS)

        await self.build_job(outlook)()

        self.assertEqual(self.bot.sent, [])

    async def test_the_regime_lifting_leaves_the_board_where_it_is(self):
        """Forgetting the spell must not delete the card the family is reading."""
        await self.build_job(build_outlook(OutageScheduleStatus.EMERGENCY_SHUTDOWNS, self.today))()

        await self.build_job(build_outlook(OutageScheduleStatus.SCHEDULE_APPLIES, self.today))()

        self.assertEqual(await self.remembered(), 0)
        self.assertEqual(self.bot.sent, [])
