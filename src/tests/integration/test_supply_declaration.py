from datetime import timedelta
from types import SimpleNamespace

from src.bot.handlers.power.jobs import EcoFlowPollJob, MainsWatchJob
from src.bot.handlers.power.messages import POWER_SUPPLY_BUTTON_STATION
from src.infrastructure.db.uow import UnitOfWork
from src.modules.power.domain import DeclaredSupply
from src.modules.power.use_cases.declare_supply import DeclareSupplyUseCase
from src.modules.power.use_cases.retrieve_declared_supply import RetrieveDeclaredSupplyUseCase
from src.tests.fakes import StubForumTopic
from src.tests.integration.base import FROZEN_NOW, BaseIntegrationTestCase
from src.tests.integration.test_mains_detection import hat, idle_and_full, on_battery, on_grid

CHAT_ID = -1001234567890


class RecordingBot:
    def __init__(self):
        self.sent: list[tuple[str, object]] = []

    async def send_message(self, chat_id, message_thread_id, text, reply_markup=None, **options):
        self.sent.append((text, reply_markup))
        return SimpleNamespace(message_id=1, chat=SimpleNamespace(id=chat_id))


class StubUps:
    def __init__(self, mains_present: bool):
        self.mains_present = mains_present

    async def read_state(self):
        return hat(mains_present=self.mains_present)


class StubStation:
    def __init__(self, state=None):
        self.state = state

    async def read_state(self, refresh: bool = False):
        return self.state


class SupplyDeclarationTestCase(BaseIntegrationTestCase):
    """
    Who is feeding the socket the hat measures — the one fact about the grid no sensor here can give.

    the hat is wired to a wall socket, so «mains voltage present» is the city only while the pi hangs on the
    wall. move it onto the station to keep the internet alive through a blackout and the same reading makes
    the bot announce the light coming back in the middle of the outage, restart the outage clock, and write a
    row the journal counts hours from. so the bot asks, and a person answers.
    """

    def uow_factory(self) -> UnitOfWork:
        return UnitOfWork(session_factory=self.session_factory)

    def build_watch(self, bot, mains_present: bool, station=None) -> MainsWatchJob:
        return MainsWatchJob(
            bot=bot,
            chat_id=CHAT_ID,
            power_topic=StubForumTopic(),
            pi_ups=StubUps(mains_present),
            ecoflow_station=StubStation(station),
            settings=SimpleNamespace(ECOFLOW_MAINS_CONFIRMATIONS=1),
            uow_factory=self.uow_factory,
            household_calendar=self.household_calendar,
        )

    def build_poll(self, station) -> EcoFlowPollJob:
        return EcoFlowPollJob(
            ecoflow_station=StubStation(station),
            uow_factory=self.uow_factory,
            household_calendar=self.household_calendar,
            timezone=self.household_calendar.timezone,
            conserved_after=timedelta(hours=6),
        )

    async def declared(self) -> DeclaredSupply:
        return await RetrieveDeclaredSupplyUseCase(uow=self.uow_factory())()

    async def declare(self, supply: DeclaredSupply, retract: int | None = None) -> bool:
        return await DeclareSupplyUseCase(uow=self.uow_factory(), household_calendar=self.household_calendar)(
            supply, retract_grid_event_id=retract
        )

    async def journal(self) -> list[str]:
        async with self.uow_factory() as uow:
            return [event.state for event in await uow.grid_events.list_since(FROZEN_NOW - timedelta(days=1))]

    async def latest_event_id(self) -> int:
        async with self.uow_factory() as uow:
            return (await uow.grid_events.retrieve_latest()).id

    async def go_dark_then_see_mains(self, bot, station=None) -> None:
        """The shape of every blackout the pi lives through: the socket dies, and later it is alive again."""
        await self.build_watch(bot, mains_present=False)()
        self.household_calendar.frozen_now += timedelta(hours=2)
        await self.build_watch(bot, mains_present=True, station=station)()

    async def test_nothing_declared_reads_as_the_grid(self):
        """Every reading means what it always meant until somebody says otherwise."""
        self.assertEqual(await self.declared(), DeclaredSupply.GRID)

    async def test_a_light_the_station_contradicts_is_announced_with_the_question(self):
        bot = RecordingBot()

        await self.go_dark_then_see_mains(bot, station=on_battery())

        text, keyboard = bot.sent[-1]
        self.assertEqual(
            text,
            "💡 <b>Світло є</b> (не було 2 год)\n\nТочно мережа? Delta 2 віддає 90 Вт і не заряджається.",
        )
        self.assertEqual([button.text for button in keyboard.inline_keyboard[0]], ["Так, мережа", "Ні, це Delta 2"])

    async def test_a_light_a_charging_station_confirms_is_announced_without_a_question(self):
        """A station drawing from the wall proves the wall is live — there is nothing left to ask."""
        bot = RecordingBot()

        await self.go_dark_then_see_mains(bot, station=on_grid())

        text, keyboard = bot.sent[-1]
        self.assertEqual(text, "💡 <b>Світло є</b> (не було 2 год)")
        self.assertEqual([button.text for button in keyboard.inline_keyboard[0]], ["Ні, це Delta 2"])

    async def test_a_light_an_idle_station_cannot_speak_about_is_announced_without_a_question(self):
        bot = RecordingBot()

        await self.go_dark_then_see_mains(bot, station=idle_and_full())

        text, keyboard = bot.sent[-1]
        self.assertEqual(text, "💡 <b>Світло є</b> (не було 2 год)")
        self.assertEqual([button.text for button in keyboard.inline_keyboard[0]], ["Ні, це Delta 2"])

    async def test_a_light_with_the_station_off_bluetooth_is_announced_without_a_question(self):
        bot = RecordingBot()

        await self.go_dark_then_see_mains(bot, station=None)

        text, keyboard = bot.sent[-1]
        self.assertEqual(text, "💡 <b>Світло є</b> (не було 2 год)")
        self.assertEqual([button.text for button in keyboard.inline_keyboard[0]], ["Ні, це Delta 2"])

    async def test_the_outage_push_carries_no_buttons_at_all(self):
        """Nothing has happened yet to correct; the mark lives on the board, which is still there later."""
        bot = RecordingBot()

        await self.build_watch(bot, mains_present=False)()

        self.assertEqual(bot.sent[-1], ("🕯 <b>Світло зникло</b>", None))

    async def test_declaring_the_station_retracts_the_announcement_the_button_names(self):
        bot = RecordingBot()
        await self.go_dark_then_see_mains(bot, station=on_battery())

        retracted = await self.declare(DeclaredSupply.STATION, retract=await self.latest_event_id())

        self.assertTrue(retracted)
        self.assertEqual(await self.journal(), ["on_battery"])

    async def test_declaring_the_station_from_a_card_a_later_change_has_overtaken_retracts_nothing(self):
        """A week-old «так, мережа» must not cut a hole in the middle of the journal."""
        bot = RecordingBot()
        await self.go_dark_then_see_mains(bot, station=on_battery())
        stale = await self.latest_event_id()
        self.household_calendar.frozen_now += timedelta(hours=3)
        await self.build_watch(bot, mains_present=False)()

        retracted = await self.declare(DeclaredSupply.STATION, retract=stale)

        self.assertFalse(retracted)
        self.assertEqual(await self.journal(), ["on_battery", "on_grid", "on_battery"])

    async def test_declaring_the_station_with_no_announcement_to_take_back_writes_only_the_declaration(self):
        bot = RecordingBot()
        await self.build_watch(bot, mains_present=False)()

        retracted = await self.declare(DeclaredSupply.STATION)

        self.assertFalse(retracted)
        self.assertEqual(await self.declared(), DeclaredSupply.STATION)
        self.assertEqual(await self.journal(), ["on_battery"])

    async def test_a_socket_the_station_is_declared_to_feed_announces_nothing_about_the_city(self):
        bot = RecordingBot()
        await self.go_dark_then_see_mains(bot, station=on_battery())
        await self.declare(DeclaredSupply.STATION, retract=await self.latest_event_id())
        said_before = len(bot.sent)

        self.household_calendar.frozen_now += timedelta(minutes=30)
        await self.build_watch(bot, mains_present=True, station=on_battery())()

        self.assertEqual(len(bot.sent), said_before)
        self.assertEqual(await self.journal(), ["on_battery"])

    async def test_the_light_declared_back_is_announced_with_the_whole_outage_behind_it(self):
        """The span is the half of the message the family repeats, and the retraction is what keeps it true."""
        bot = RecordingBot()
        await self.go_dark_then_see_mains(bot, station=on_battery())
        await self.declare(DeclaredSupply.STATION, retract=await self.latest_event_id())
        watch = self.build_watch(bot, mains_present=True, station=on_battery())
        await watch()
        self.household_calendar.frozen_now += timedelta(hours=1)
        await self.declare(DeclaredSupply.GRID)

        await watch()

        text, keyboard = bot.sent[-1]
        self.assertEqual(text, "💡 <b>Світло є</b> (не було 3 год)")
        self.assertEqual([button.text for button in keyboard.inline_keyboard[0]], ["Ні, це Delta 2"])

    async def test_the_light_the_family_declared_back_is_not_questioned_in_return(self):
        """They have just answered the question; asking it again under their own answer reads as deaf."""
        bot = RecordingBot()
        await self.go_dark_then_see_mains(bot, station=on_battery())
        await self.declare(DeclaredSupply.STATION, retract=await self.latest_event_id())
        watch = self.build_watch(bot, mains_present=True, station=on_battery())
        await watch()
        await self.declare(DeclaredSupply.GRID)

        await watch()

        # the correction is still there, because the station may be asleep the next time it matters —
        # what must not come back is the question, and the «так, мережа» that answers it
        self.assertEqual([button.text for button in bot.sent[-1][1].inline_keyboard[0]], ["Ні, це Delta 2"])
        self.assertNotIn("Точно мережа?", bot.sent[-1][0])

    async def test_a_station_charging_from_the_wall_releases_the_declaration(self):
        """Otherwise «ні, це Delta 2» silences «світло є» until somebody remembers to take it back."""
        await self.declare(DeclaredSupply.STATION)

        await self.build_poll(on_grid())()

        self.assertEqual(await self.declared(), DeclaredSupply.GRID)

    async def test_a_station_still_feeding_the_flat_leaves_the_declaration_alone(self):
        await self.declare(DeclaredSupply.STATION)

        await self.build_poll(on_battery())()

        self.assertEqual(await self.declared(), DeclaredSupply.STATION)

    async def test_a_station_off_bluetooth_leaves_the_declaration_alone(self):
        await self.declare(DeclaredSupply.STATION)

        await self.build_poll(None)()

        self.assertEqual(await self.declared(), DeclaredSupply.STATION)

    async def test_the_question_names_the_row_it_would_retract(self):
        bot = RecordingBot()

        await self.go_dark_then_see_mains(bot, station=on_battery())

        keyboard = bot.sent[-1][1]
        station_button = next(
            button for button in keyboard.inline_keyboard[0] if button.text == POWER_SUPPLY_BUTTON_STATION
        )
        self.assertEqual(station_button.callback_data, f"supply:station:{await self.latest_event_id()}:0:0")

    async def test_the_hat_losing_mains_releases_a_station_declaration_that_has_had_its_grace(self):
        """«Я перемкнувся назад» without a button: the pi's socket going dark is the proof."""
        bot = RecordingBot()
        await self.declare(DeclaredSupply.STATION)
        self.household_calendar.frozen_now += timedelta(minutes=11)

        await self.build_watch(bot, mains_present=False)()

        self.assertEqual(await self.declared(), DeclaredSupply.GRID)

    async def test_the_hat_losing_mains_within_the_grace_leaves_the_declaration_alone(self):
        """The mark and the plug do not move in the same second, and the tap often comes first."""
        bot = RecordingBot()
        await self.declare(DeclaredSupply.STATION)
        self.household_calendar.frozen_now += timedelta(minutes=2)

        await self.build_watch(bot, mains_present=False)()

        self.assertEqual(await self.declared(), DeclaredSupply.STATION)

    async def test_a_station_declaration_survives_while_the_hat_still_reads_mains(self):
        """Mains at the hat is exactly what a station feeding it predicts — it contradicts nothing."""
        bot = RecordingBot()
        await self.declare(DeclaredSupply.STATION)
        self.household_calendar.frozen_now += timedelta(hours=2)

        await self.build_watch(bot, mains_present=True, station=on_battery())()

        self.assertEqual(await self.declared(), DeclaredSupply.STATION)

    async def test_the_light_coming_back_after_a_released_declaration_is_announced(self):
        """The whole point: nobody has to remember the mark for «світло є» to arrive."""
        bot = RecordingBot()
        await self.build_watch(bot, mains_present=False)()
        await self.declare(DeclaredSupply.STATION)
        self.household_calendar.frozen_now += timedelta(minutes=11)
        await self.build_watch(bot, mains_present=False)()
        self.household_calendar.frozen_now += timedelta(hours=1)

        await self.build_watch(bot, mains_present=True, station=idle_and_full())()

        self.assertEqual(bot.sent[-1][0], "💡 <b>Світло є</b> (не було 1 год 11 хв)")
