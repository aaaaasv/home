"""The scheduled job that re-reads tracked prices and announces a drop."""
import logging
from collections.abc import Callable

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.bot.handlers.shopping.formatting import render_price_drop_alert, render_price_watch_broken
from src.bot.scheduling import SchedulerContext
from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.common.time import current_time
from src.infrastructure.db.uow import UnitOfWork
from src.modules.shopping.services.price_source import PriceSource
from src.modules.shopping.use_cases.check_tracked_prices import CheckTrackedPricesUseCase

logger = logging.getLogger(__name__)


class PriceWatchJob:
    """
    Re-reads every tracked shopping item once a day and speaks only when one hits a new low. it is dormant until
    someone /tracks a link, so it fits the shopping topic's no-digest rule — an event, not a daily message.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        shopping_topic: ForumTopicRegistry,
        uow_factory: Callable[[], UnitOfWork],
        price_source: PriceSource,
        tech_topic: ForumTopicRegistry | None = None,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.shopping_topic = shopping_topic
        self.uow_factory = uow_factory
        self.price_source = price_source
        self.tech_topic = tech_topic

    async def __call__(self) -> None:
        outcome = await CheckTrackedPricesUseCase(
            uow=self.uow_factory(), price_source=self.price_source, checked_at=current_time()
        )()

        if outcome.drops:
            topic_id = await self.shopping_topic.resolve()
            for drop in outcome.drops:
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    message_thread_id=topic_id,
                    text=render_price_drop_alert(drop),
                    # the tracked item hit a new low — the event someone asked to be told about
                    disable_notification=False,
                )

        # a page that stopped yielding a price is a broken parser or a redesigned site — say it once, in service
        # low urgency and tech-topic only, so it rides the silent default: it will be seen, it need not buzz
        if outcome.failures and self.tech_topic is not None:
            await self.bot.send_message(
                chat_id=self.chat_id,
                message_thread_id=await self.tech_topic.resolve(),
                text=render_price_watch_broken(outcome.failures),
            )
        logger.info("Price watch: %s drop(s), %s failure(s)", len(outcome.drops), len(outcome.failures))


def register_jobs(scheduler: AsyncIOScheduler, context: SchedulerContext) -> None:
    """Re-read every tracked price once a day, at an hour when a drop is still worth acting on."""
    settings = context.settings
    price_watch_job = PriceWatchJob(
        bot=context.bot,
        chat_id=settings.TELEGRAM_REMINDER_CHAT_ID,
        shopping_topic=context.shopping_topic,
        uow_factory=context.uow_factory,
        price_source=context.price_source,
        tech_topic=context.tech_topic,
    )
    price_watch_time = settings.price_watch_time
    scheduler.add_job(
        price_watch_job.__call__,
        trigger=CronTrigger(hour=price_watch_time.hour, minute=price_watch_time.minute),
        id="price_watch",
        replace_existing=True,
    )
