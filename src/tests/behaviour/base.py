"""
Drives real updates through the real dispatcher, which is the one layer 566 tests never touched.

The dispatcher is built **once for the whole process**, because `build_dispatcher` attaches filters to
module-level routers and a second call would stack duplicates onto the same globals. That is not a limit on
what can be tested: `feed_update` merges its keyword arguments over the dispatcher's workflow data, so every
test still supplies its own database, its own storage and its own boards.
"""
from types import SimpleNamespace

from aiogram import Bot, Dispatcher
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.bot.application import build_dispatcher
from src.common.config import Settings
from src.infrastructure.db.base import Base
from src.infrastructure.db.main import apply_sqlite_pragmas
from src.infrastructure.db.uow import UnitOfWork
from src.tests.fakes import FrozenHouseholdCalendar, RecordingPhotoStorage, StubForumTopic
from src.tests.integration.base import FROZEN_NOW, KYIV, BaseIntegrationTestCase
from src.tests.telegram import (
    ACTOR_ID,
    CHAT_ID,
    CHORES_TOPIC,
    PLACES_TOPIC,
    PLANTS_TOPIC,
    SHOPPING_TOPIC,
    RecordingSession,
    build_bot,
)

_dispatcher: Dispatcher | None = None
_bot: Bot | None = None


class NullBoard:
    """A board that records nothing and refuses nothing — the cards themselves have their own tests"""

    def __init__(self) -> None:
        self.refreshed = 0

    async def refresh(self, *args, **kwargs) -> None:
        self.refreshed += 1

    async def post(self, *args, **kwargs) -> None:
        self.refreshed += 1


def build_settings() -> Settings:
    return Settings(
        TELEGRAM_BOT_TOKEN="8000000000:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        TELEGRAM_ALLOWED_USER_IDS=str(ACTOR_ID),
        TELEGRAM_REMINDER_CHAT_ID=CHAT_ID,
    )


def shared_dispatcher() -> tuple[Dispatcher, Bot]:
    """One dispatcher for the process; the per-test parts are handed in with each update instead."""
    global _dispatcher, _bot
    if _dispatcher is None:
        _bot = build_bot(RecordingSession())
        _dispatcher = build_dispatcher(
            bot=_bot,
            settings=build_settings(),
            care_topic=StubForumTopic(thread_id=PLANTS_TOPIC),
            shopping_topic=StubForumTopic(thread_id=SHOPPING_TOPIC),
            shopping_list_board=NullBoard(),
            places_topic=StubForumTopic(thread_id=PLACES_TOPIC),
            places_board=NullBoard(),
            chores_topic=StubForumTopic(thread_id=CHORES_TOPIC),
            chores_board=NullBoard(),
            ecoflow_station=SimpleNamespace(),
            air_conditioner=SimpleNamespace(),
        )
    return _dispatcher, _bot


class BaseBehaviourTestCase(BaseIntegrationTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
        apply_sqlite_pragmas(self.engine)
        self.session_factory = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        self.uow = UnitOfWork(session_factory=self.session_factory)
        self.household_calendar = FrozenHouseholdCalendar(timezone=KYIV, frozen_now=FROZEN_NOW)
        self.today = self.household_calendar.today()

        self.dispatcher, self.bot = shared_dispatcher()
        self.session: RecordingSession = self.bot.session
        self.session.calls.clear()
        await self.dispatcher.storage.close()
        self.photo_storage = RecordingPhotoStorage(local_path="photos/unique-abc.jpg")
        self.shopping_list_board = NullBoard()

    def uow_factory(self) -> UnitOfWork:
        return UnitOfWork(session_factory=self.session_factory)

    async def feed(self, update, **overrides):
        """One update, with this test's own database and collaborators laid over the dispatcher's."""
        return await self.dispatcher.feed_update(
            self.bot,
            update,
            uow_factory=self.uow_factory,
            household_calendar=self.household_calendar,
            photo_storage=self.photo_storage,
            shopping_list_board=self.shopping_list_board,
            **overrides,
        )
