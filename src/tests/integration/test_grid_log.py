from datetime import timedelta
from types import SimpleNamespace

from src.bot.handlers.power.jobs import MainsWatchJob
from src.infrastructure.db.uow import UnitOfWork
from src.modules.power.domain import EcoFlowState, GridState
from src.tests.fakes import StubForumTopic
from src.tests.integration.base import FROZEN_NOW, BaseIntegrationTestCase
from src.tests.integration.test_mains_detection import hat, on_battery, on_grid

CHAT_ID = -1001234567890


class RecordingBot:
    def __init__(self):
        self.sent: list[str] = []

    async def send_message(self, chat_id, message_thread_id, text, **options):
        self.sent.append(text)
        return SimpleNamespace(message_id=1, chat=SimpleNamespace(id=chat_id))


class StubStation:
    def __init__(self, state):
        self.state = state

    async def read_state(self):
        return self.state


class StubUps:
    def __init__(self, mains_present: bool):
        self.mains_present = mains_present

    async def read_state(self):
        return hat(mains_present=self.mains_present)


class GridLogTestCase(BaseIntegrationTestCase):
    """
    Every time the grid went or came back, written down.

    the monitor held this in memory and re-seeded after a restart, so «скільки годин ми були без світла в
    жовтні» had no answer at all — in the one layer the whole system is built around.
    """

    def uow_factory(self) -> UnitOfWork:
        return UnitOfWork(session_factory=self.session_factory)

    def build_job(self, bot, mains_present: bool, ecoflow: EcoFlowState) -> MainsWatchJob:
        return MainsWatchJob(
            bot=bot,
            chat_id=CHAT_ID,
            power_topic=StubForumTopic(),
            ecoflow_station=StubStation(ecoflow),
            pi_ups=StubUps(mains_present),
            settings=SimpleNamespace(ECOFLOW_MAINS_CONFIRMATIONS=1, PI_UPS_FED_BY_STATION=False),
            uow_factory=self.uow_factory,
            household_calendar=self.household_calendar,
        )

    async def logged(self) -> list[str]:
        async with self.uow_factory() as uow:
            return [event.state for event in await uow.grid_events.list_since(FROZEN_NOW - timedelta(days=1))]

    async def test_the_grid_going_is_written_down_as_well_as_announced(self):
        bot = RecordingBot()
        job = self.build_job(bot, mains_present=True, ecoflow=on_grid())
        await job()
        job.pi_ups = StubUps(mains_present=False)

        await job()

        self.assertEqual(await self.logged(), [GridState.ON_BATTERY.value])
        self.assertEqual(len(bot.sent), 1)

    async def test_the_grid_returning_is_written_down_too(self):
        bot = RecordingBot()
        job = self.build_job(bot, mains_present=False, ecoflow=on_battery())
        await job()
        job.pi_ups = StubUps(mains_present=True)
        job.ecoflow_station = StubStation(on_grid())

        await job()

        self.assertEqual(await self.logged(), [GridState.ON_GRID.value])

    async def test_a_poll_that_changes_nothing_writes_nothing(self):
        bot = RecordingBot()
        job = self.build_job(bot, mains_present=True, ecoflow=on_grid())

        for _ in range(3):
            await job()

        self.assertEqual(await self.logged(), [])
        self.assertEqual(bot.sent, [])
