from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from src.bot.handlers.newspaper.jobs import WeeklyNewspaperJob
from src.bot.handlers.newspaper.rendering import HalfPageRenderer
from src.modules.newspaper.services.word_source import WordBank
from src.modules.power.domain import OutageInterval, OutageSchedule, OutageScheduleStatus
from src.tests.fakes import (
    FixedOutageScheduleProvider,
    FrozenHouseholdCalendar,
    RecordingBot,
    RecordingPrintQueue,
    StubForumTopic,
)
from src.tests.integration.base import BaseIntegrationTestCase

KYIV = ZoneInfo("Europe/Kyiv")
SATURDAY = 5


def local(day: int, hour: int, minute: int = 0) -> datetime:
    # september 2026: the 18th is a friday, the 19th a saturday, the 20th a sunday
    return datetime(2026, 9, day, hour, minute, tzinfo=KYIV)


class WeeklyNewspaperJobTestCase(BaseIntegrationTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.bot = RecordingBot()
        self.print_queue = RecordingPrintQueue()

    def build_job(self, moment: datetime, schedule: OutageSchedule | None = None) -> WeeklyNewspaperJob:
        return WeeklyNewspaperJob(
            bot=self.bot,
            chat_id=-100,
            tech_topic=StubForumTopic(thread_id=7),
            uow_factory=lambda: self.uow,
            household_calendar=FrozenHouseholdCalendar(timezone=KYIV, frozen_now=moment),
            word_sources=[WordBank()],
            renderer=HalfPageRenderer(title=""),
            print_queue=self.print_queue,
            schedule_provider=FixedOutageScheduleProvider(schedule),
            print_weekday=SATURDAY,
            print_time=time(13, 0),
            title="",
        )

    async def test_weekly_newspaper_job_at_saturday_lunchtime_sends_the_first_issue_to_the_printer(self):
        job = self.build_job(local(19, 13))

        await job()

        self.assertEqual([name for name, _ in self.print_queue.jobs], ["Щотижневик № 1"])
        self.assertTrue(self.print_queue.jobs[0][1].startswith(b"%PDF"))

    async def test_weekly_newspaper_job_half_an_hour_after_printing_sends_nothing_more(self):
        await self.build_job(local(19, 13))()

        await self.build_job(local(19, 13, 30))()

        self.assertEqual(len(self.print_queue.jobs), 1)

    async def test_weekly_newspaper_job_on_friday_evening_sends_nothing(self):
        job = self.build_job(local(18, 21))

        await job()

        self.assertEqual(self.print_queue.jobs, [])

    async def test_weekly_newspaper_job_with_an_outage_due_in_ten_minutes_holds_the_page_back(self):
        schedule = OutageSchedule(
            day=date(2026, 9, 19),
            status=OutageScheduleStatus.SCHEDULE_APPLIES,
            off_intervals=(OutageInterval(13 * 60 + 10, 16 * 60),),
            updated_on=None,
        )
        job = self.build_job(local(19, 13), schedule=schedule)

        await job()

        self.assertEqual(self.print_queue.jobs, [])

    async def test_weekly_newspaper_job_when_the_printer_fails_on_saturday_stays_silent(self):
        self.print_queue.printed = False
        job = self.build_job(local(19, 13))

        await job()

        self.assertEqual(self.bot.sent, [])

    async def test_weekly_newspaper_job_when_the_last_attempt_fails_tells_the_service_topic(self):
        self.print_queue.printed = False
        await self.build_job(local(19, 13))()

        await self.build_job(local(20, 20, 30))()

        self.assertEqual(
            [(message["message_thread_id"], message["text"]) for message in self.bot.sent],
            [
                (
                    7,
                    "🖨 Щотижневик № 1 не надрукувався: принтер так і не відповів. "
                    "Перевір, чи Epson увімкнений і чи є в лотку папір — наступний номер вийде у звичний час.",
                )
            ],
        )
