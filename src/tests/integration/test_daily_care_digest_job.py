from src.bot.handlers.plants.jobs import DailyCareDigestJob
from src.bot.services.posted_message_tracker import PostedMessageTracker
from src.common.config import get_settings
from src.common.constants import CareTaskType
from src.infrastructure.db.uow import UnitOfWork
from src.tests.fakes import RecordingBot, StubForumTopic
from src.tests.integration.base import BaseIntegrationTestCase

CHAT_ID = -1001234567890


class DailyCareDigestNotificationTestCase(BaseIntegrationTestCase):
    def uow_factory(self) -> UnitOfWork:
        return UnitOfWork(session_factory=self.session_factory)

    async def seed_due_plant(self, name: str) -> None:
        plant_id = await self.seed_plant(name=name)
        await self.seed_care_schedule(
            plant_id=plant_id, task_type=CareTaskType.WATERING, interval_days=7, next_due_on=self.today
        )

    async def run_digest(self) -> RecordingBot:
        bot = RecordingBot()
        settings = get_settings()
        await DailyCareDigestJob(
            bot=bot,
            chat_id=CHAT_ID,
            care_topic=StubForumTopic(),
            uow_factory=self.uow_factory,
            household_calendar=self.household_calendar,
            settings=settings,
            posted_message_tracker=PostedMessageTracker(bot=bot, uow_factory=self.uow_factory),
        )()
        return bot

    async def test_digest_with_several_plants_due_notifies_only_once(self):
        for name in ("Кактус", "Монстера", "Фікус"):
            await self.seed_due_plant(name)

        bot = await self.run_digest()

        self.assertEqual(len(bot.sent), 3)
        self.assertEqual([message["silent"] for message in bot.sent], [False, True, True])

    async def test_digest_with_one_plant_due_still_notifies(self):
        await self.seed_due_plant("Кактус")

        bot = await self.run_digest()

        self.assertEqual([message["silent"] for message in bot.sent], [False])
