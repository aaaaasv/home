from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from src.bot.handlers.power.jobs import YasnoScheduleJob
from src.bot.handlers.power.messages import POWER_OUTAGE_EMERGENCY
from src.bot.services.posted_message_tracker import OUTAGE_EMERGENCY_KIND
from src.infrastructure.db.uow import UnitOfWork
from src.modules.power.domain import OutageOutlook, OutageSchedule, OutageScheduleStatus
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
    async def refresh(self, outlook=None) -> bool:
        return True

    async def post(self, outlook=None) -> None:
        return None


def build_outlook(status: OutageScheduleStatus, day: date) -> OutageOutlook:
    return OutageOutlook(today=OutageSchedule(day=day, status=status, off_intervals=(), updated_on=None), tomorrow=None)


class EmergencyAnnouncementTestCase(BaseIntegrationTestCase):
    """
    One ping when the group goes onto emergency shutdowns, and nothing more until it comes back off.

    it was keyed on the calendar day, so a spell lasting past midnight announced itself again at 00:06 — a
    notification, at night, repeating what had been said that morning and what the board already showed.
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
            outage_schedule_board=StubBoard(),
            settings=SimpleNamespace(YASNO_PRE_OUTAGE_LEAD_MINUTES=30),
            timezone=KYIV,
        )

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.bot = RecordingBot()
        self.today = datetime.now(KYIV).date()
        self.tomorrow = date.fromordinal(self.today.toordinal() + 1)

    async def remembered(self) -> int:
        async with self.uow_factory() as uow:
            return len(await uow.posted_messages.list_by_kind(OUTAGE_EMERGENCY_KIND))

    async def test_the_group_going_onto_emergency_shutdowns_is_announced_once(self):
        await self.build_job(build_outlook(OutageScheduleStatus.EMERGENCY_SHUTDOWNS, self.today))()

        self.assertEqual(self.bot.sent, [POWER_OUTAGE_EMERGENCY])
        self.assertEqual(await self.remembered(), 1)

    async def test_the_same_spell_polled_again_says_nothing(self):
        job = self.build_job(build_outlook(OutageScheduleStatus.EMERGENCY_SHUTDOWNS, self.today))
        await job()

        await job()

        self.assertEqual(self.bot.sent, [POWER_OUTAGE_EMERGENCY])

    async def test_a_spell_that_lasts_past_midnight_is_not_announced_again(self):
        """The 00:06 ping: the day rolled over, the regime did not."""
        await self.build_job(build_outlook(OutageScheduleStatus.EMERGENCY_SHUTDOWNS, self.today))()

        await self.build_job(build_outlook(OutageScheduleStatus.EMERGENCY_SHUTDOWNS, self.tomorrow))()

        self.assertEqual(self.bot.sent, [POWER_OUTAGE_EMERGENCY])

    async def test_an_ordinary_day_announces_nothing(self):
        await self.build_job(build_outlook(OutageScheduleStatus.SCHEDULE_APPLIES, self.today))()

        self.assertEqual(self.bot.sent, [])
        self.assertEqual(await self.remembered(), 0)

    async def test_a_new_spell_after_the_regime_lifted_is_announced_again(self):
        await self.build_job(build_outlook(OutageScheduleStatus.EMERGENCY_SHUTDOWNS, self.today))()
        await self.build_job(build_outlook(OutageScheduleStatus.SCHEDULE_APPLIES, self.today))()

        await self.build_job(build_outlook(OutageScheduleStatus.EMERGENCY_SHUTDOWNS, self.today))()

        self.assertEqual(self.bot.sent, [POWER_OUTAGE_EMERGENCY, POWER_OUTAGE_EMERGENCY])

    async def test_the_regime_lifting_leaves_the_announcement_in_the_topic(self):
        """It is a record of what happened; forgetting it must not rewrite the history of the chat."""
        await self.build_job(build_outlook(OutageScheduleStatus.EMERGENCY_SHUTDOWNS, self.today))()

        await self.build_job(build_outlook(OutageScheduleStatus.SCHEDULE_APPLIES, self.today))()

        self.assertEqual(await self.remembered(), 0)
        self.assertEqual(self.bot.sent, [POWER_OUTAGE_EMERGENCY])
