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
        job = self.build_job(bot, mains_present=True, ecoflow=on_grid())
        await job()
        job.pi_ups = StubUps(mains_present=False)
        job.ecoflow_station = StubStation(on_battery())
        await job()
        job.pi_ups = StubUps(mains_present=True)
        job.ecoflow_station = StubStation(on_grid())

        await job()

        self.assertEqual(await self.logged(), [GridState.ON_BATTERY.value, GridState.ON_GRID.value])

    async def test_a_restart_inside_an_outage_already_announced_keeps_quiet_about_it(self):
        """The record is what a restart reads its bearings from, so the push does not arrive twice."""
        async with self.uow_factory() as uow:
            await uow.grid_events.create({"state": GridState.ON_BATTERY.value, "at": FROZEN_NOW})
        bot = RecordingBot()
        job = self.build_job(bot, mains_present=False, ecoflow=on_battery())

        for _ in range(3):
            await job()

        self.assertEqual(bot.sent, [])

    async def test_a_restart_inside_an_outage_still_announces_the_grid_coming_back(self):
        async with self.uow_factory() as uow:
            await uow.grid_events.create({"state": GridState.ON_BATTERY.value, "at": FROZEN_NOW})
        bot = RecordingBot()
        job = self.build_job(bot, mains_present=True, ecoflow=on_grid())

        await job()

        self.assertEqual(bot.sent, ["💡 <b>Світло є</b>"])

    async def test_an_outage_that_began_before_the_bot_could_read_anything_is_announced_on_the_first_reading(self):
        """
        The nine outages of 7–9 october: the hat saw every one of them and the family was told about none.

        nothing had been recorded, so there was no state to resume from, and the first known reading was
        treated as establishing a baseline rather than as the blackout it was.
        """
        bot = RecordingBot()
        job = self.build_job(bot, mains_present=False, ecoflow=on_battery())

        await job()

        self.assertEqual(bot.sent, ["🕯 <b>Світло зникло</b>"])
        self.assertEqual(await self.logged(), [GridState.ON_BATTERY.value])

    async def test_a_poll_that_changes_nothing_writes_nothing(self):
        bot = RecordingBot()
        job = self.build_job(bot, mains_present=True, ecoflow=on_grid())

        for _ in range(3):
            await job()

        self.assertEqual(await self.logged(), [])
        self.assertEqual(bot.sent, [])
