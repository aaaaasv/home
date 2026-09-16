"""The weekly paper: printed once a week, retried until it prints, and silent unless it never does."""
import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, time, timedelta

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.bot.handlers.newspaper import messages
from src.bot.handlers.newspaper.rendering import HalfPageRenderer
from src.bot.scheduling import SchedulerContext
from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.newspaper.domain import CrosswordNotBuiltError, NewspaperIssue
from src.modules.newspaper.print_window import is_inside_window, is_last_attempt
from src.modules.newspaper.services.issue_renderer import IssueRenderer
from src.modules.newspaper.services.print_queue import PrintQueue
from src.modules.newspaper.services.word_source import WordSource
from src.modules.newspaper.use_cases.mark_issue_printed import MarkIssuePrintedUseCase
from src.modules.newspaper.use_cases.prepare_issue import PrepareIssueUseCase
from src.modules.power.services.outage_schedule_provider import OutageScheduleProvider

logger = logging.getLogger(__name__)

RETRY_INTERVAL = timedelta(minutes=30)
# a scheduled outage that starts this soon could cut the power mid-page, which can leave the print head uncapped
OUTAGE_MARGIN_MINUTES = 20
PRINT_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class WeeklyNewspaperJob:
    """
    Prints this week's issue at the set hour, and keeps trying every half hour until it has.

    it runs every half hour all week and does nothing outside the window, because a pi that was down or a printer
    that was off at the set hour should still produce the week's page later that day. the page is the point:
    an inkjet that fires no ink for a week starts to clog, so a skipped week is worth one message — sent once,
    only after the last attempt, to the service topic.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        tech_topic: ForumTopicRegistry | None,
        uow_factory: Callable[[], UnitOfWork],
        household_calendar: HouseholdCalendar,
        word_sources: list[WordSource],
        renderer: IssueRenderer,
        print_queue: PrintQueue,
        schedule_provider: OutageScheduleProvider | None,
        print_weekday: int,
        print_time: time,
        title: str,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.tech_topic = tech_topic
        self.uow_factory = uow_factory
        self.household_calendar = household_calendar
        self.word_sources = word_sources
        self.renderer = renderer
        self.print_queue = print_queue
        self.schedule_provider = schedule_provider
        self.print_weekday = print_weekday
        self.print_time = print_time
        self.title = title or messages.DEFAULT_TITLE

    async def __call__(self) -> None:
        local_now = self.household_calendar.now().astimezone(self.household_calendar.timezone)
        if not is_inside_window(local_now, self.print_weekday, self.print_time):
            return

        try:
            issue = await PrepareIssueUseCase(
                uow=self.uow_factory(), household_calendar=self.household_calendar, word_sources=self.word_sources
            )()
        except CrosswordNotBuiltError:
            logger.exception("Weekly paper has no crossword this attempt")
            return
        if issue is None:
            return
        if await self._is_outage_due(local_now):
            logger.info("Weekly paper no. %s held back: a scheduled outage is on or about to start", issue.number)
            return

        document = await asyncio.to_thread(self.renderer.render, issue, local_now.date())
        job_name = messages.JOB_NAME.format(title=self.title, number=issue.number)
        if await self.print_queue.print_document(document, job_name):
            await MarkIssuePrintedUseCase(uow=self.uow_factory(), household_calendar=self.household_calendar)(issue.id)
            logger.info("Printed weekly paper no. %s", issue.number)
            return

        if is_last_attempt(local_now, self.print_weekday, self.print_time, RETRY_INTERVAL):
            await self._announce_failure(issue)

    async def _is_outage_due(self, local_now: datetime) -> bool:
        if self.schedule_provider is None:
            return False
        schedule = await self.schedule_provider.fetch_today()
        if schedule is None or schedule.day != local_now.date():
            return False
        if schedule.is_off_at(local_now):
            return True
        upcoming = schedule.next_off_interval(local_now)
        minute_of_day = local_now.hour * 60 + local_now.minute
        return upcoming is not None and upcoming.start_minute - minute_of_day <= OUTAGE_MARGIN_MINUTES

    async def _announce_failure(self, issue: NewspaperIssue) -> None:
        logger.warning("Weekly paper no. %s never printed this week", issue.number)
        if self.tech_topic is None:
            return
        await self.bot.send_message(
            chat_id=self.chat_id,
            message_thread_id=await self.tech_topic.resolve(),
            text=messages.PRINT_FAILED.format(title=self.title, number=issue.number),
        )


def register_jobs(scheduler: AsyncIOScheduler, context: SchedulerContext) -> None:
    """Print the weekly paper on the lan printer, once a print queue is configured."""
    settings = context.settings
    if not settings.NEWSPAPER_ENABLED or context.newspaper_print_queue is None:
        return

    job = WeeklyNewspaperJob(
        bot=context.bot,
        chat_id=settings.TELEGRAM_REMINDER_CHAT_ID,
        tech_topic=context.tech_topic,
        uow_factory=context.uow_factory,
        household_calendar=context.household_calendar,
        word_sources=list(context.newspaper_word_sources),
        renderer=HalfPageRenderer(title=settings.NEWSPAPER_TITLE),
        print_queue=context.newspaper_print_queue,
        schedule_provider=context.schedule_provider,
        print_weekday=PRINT_WEEKDAYS.index(settings.NEWSPAPER_PRINT_WEEKDAY),
        print_time=settings.newspaper_print_time,
        title=settings.NEWSPAPER_TITLE,
    )
    scheduler.add_job(
        job.__call__,
        trigger=CronTrigger(minute=f"*/{int(RETRY_INTERVAL.total_seconds() // 60)}"),
        id="weekly_newspaper",
        replace_existing=True,
        # one attempt can wait minutes on the printer; a second one must not start on top of it
        max_instances=1,
        coalesce=True,
    )
