from datetime import timedelta
from types import SimpleNamespace

from src.bot.handlers.power.jobs import PiPackWatchJob
from src.bot.services.posted_message_tracker import PI_PACK_WARNING_KIND
from src.infrastructure.db.uow import UnitOfWork
from src.modules.power.domain import PackWarning
from src.tests.fakes import StubForumTopic
from src.tests.integration.base import BaseIntegrationTestCase
from src.tests.integration.test_mains_detection import hat

CHAT_ID = -1001234567890

# the two readings the thresholds sit between: 3.54 V is 57 minutes on the measured curve, 3.42 V is ten
UNDER_AN_HOUR_VOLTS = 3.54
ABOUT_TO_HALT_VOLTS = 3.42


class RecordingBot:
    def __init__(self):
        self.sent: list[tuple[str, bool]] = []
        self.edits: list[tuple[int, str]] = []

    async def send_message(self, chat_id, message_thread_id, text, disable_notification=True, **options):
        self.sent.append((text, disable_notification))
        return SimpleNamespace(message_id=500 + len(self.sent), chat=SimpleNamespace(id=chat_id))

    async def edit_message_text(self, chat_id, message_id, text, **options):
        self.edits.append((message_id, text))
        return None

    async def delete_message(self, chat_id, message_id):
        return None


class ReadableUps:
    """The hat the job asks, with one reading at a time — swapped between ticks the way a discharge moves."""

    def __init__(self, battery_volts: float, mains_present: bool = False):
        self.reading = hat(mains_present=mains_present, battery_volts=battery_volts)

    def reads(self, battery_volts: float, mains_present: bool = False) -> None:
        self.reading = hat(mains_present=mains_present, battery_volts=battery_volts)

    async def read_state(self):
        return self.reading


class SilentUps:
    async def read_state(self):
        return None


class PackWarningTestCase(BaseIntegrationTestCase):
    """
    The pi warning the house that its own pack is emptying — twice per outage at most, and never on the grid.

    the state that keeps it to twice lives in the database rather than in the job, because a deploy in the
    middle of an outage would otherwise start the warnings over, and an outage is exactly when a restart
    happens least carefully.
    """

    def uow_factory(self) -> UnitOfWork:
        return UnitOfWork(session_factory=self.session_factory)

    def build_watch(self, bot, pi_ups) -> PiPackWatchJob:
        return PiPackWatchJob(
            bot=bot,
            chat_id=CHAT_ID,
            power_topic=StubForumTopic(),
            pi_ups=pi_ups,
            uow_factory=self.uow_factory,
            warning_at=timedelta(minutes=60),
            goodbye_at=timedelta(minutes=10),
        )

    async def lane(self) -> list[str]:
        async with self.uow_factory() as uow:
            return [posted.reference for posted in await uow.posted_messages.list_by_kind(PI_PACK_WARNING_KIND)]

    async def test_watch_a_pack_with_hours_left_says_nothing_at_all(self):
        bot = RecordingBot()

        await self.build_watch(bot, ReadableUps(battery_volts=3.90))()

        self.assertEqual((bot.sent, await self.lane()), ([], []))

    async def test_watch_a_pack_with_under_an_hour_left_names_the_measured_time_and_what_stops(self):
        bot = RecordingBot()

        await self.build_watch(bot, ReadableUps(battery_volts=UNDER_AN_HOUR_VOLTS))()

        self.assertEqual(
            bot.sent,
            [
                (
                    "🖥 <b>Pi сяде за ~57 хв</b>\n"
                    "\n"
                    "Своє живлення в нього закінчується. Коли вимкнеться — не буде бота, датчиків, "
                    "Apple Home і робочого тунелю.\n"
                    "Інтернет і Wi-Fi лишаться: роутер живиться окремо.",
                    False,
                )
            ],
        )

    async def test_watch_a_pack_under_an_hour_on_a_second_tick_does_not_warn_twice(self):
        bot = RecordingBot()
        pi_ups = ReadableUps(battery_volts=UNDER_AN_HOUR_VOLTS)
        watch = self.build_watch(bot, pi_ups)
        await watch()

        pi_ups.reads(battery_volts=3.52)
        await watch()

        self.assertEqual((len(bot.sent), await self.lane()), (1, [PackWarning.LOW.value]))

    async def test_watch_a_pack_about_to_halt_says_goodbye_and_how_to_bring_the_pi_back(self):
        bot = RecordingBot()

        await self.build_watch(bot, ReadableUps(battery_volts=ABOUT_TO_HALT_VOLTS))()

        self.assertEqual(
            bot.sent,
            [
                (
                    "🖥 <b>Pi вимикається</b>\n"
                    "\n"
                    "Пак сів — бот, датчики, Apple Home і робочий тунель зникають до світла. "
                    "Інтернет і Wi-Fi лишаються.\n"
                    "Щойно в розетці зʼявиться струм, Pi має піднятись сам — якщо за кілька хвилин тихо, "
                    "натисни кнопку на корпусі.",
                    False,
                )
            ],
        )

    async def test_watch_a_discharge_through_both_thresholds_says_each_thing_once(self):
        bot = RecordingBot()
        pi_ups = ReadableUps(battery_volts=3.90)
        watch = self.build_watch(bot, pi_ups)
        await watch()

        for volts in (UNDER_AN_HOUR_VOLTS, 3.50, ABOUT_TO_HALT_VOLTS, 3.41):
            pi_ups.reads(battery_volts=volts)
            await watch()

        self.assertEqual((len(bot.sent), await self.lane()), (2, [PackWarning.LOW.value, PackWarning.HALTING.value]))

    async def test_watch_a_pack_already_at_the_halt_on_the_first_tick_only_says_goodbye(self):
        """A bot started late in an outage skips the hour's warning rather than sending both at once."""
        bot = RecordingBot()

        await self.build_watch(bot, ReadableUps(battery_volts=3.41))()

        self.assertEqual((len(bot.sent), await self.lane()), (1, [PackWarning.HALTING.value]))

    async def test_watch_a_live_socket_after_the_warning_writes_it_over_and_clears_the_lane(self):
        bot = RecordingBot()
        pi_ups = ReadableUps(battery_volts=UNDER_AN_HOUR_VOLTS)
        watch = self.build_watch(bot, pi_ups)
        await watch()

        pi_ups.reads(battery_volts=3.56, mains_present=True)
        await watch()

        self.assertEqual(
            (bot.edits, await self.lane()),
            ([(501, "🔋 <b>Pi знову живиться</b>\n\nПак заряджається.")], []),
        )

    async def test_watch_a_live_socket_after_a_goodbye_this_run_sent_writes_the_goodbye_over(self):
        """The pi said it was going and then did not go: the message on screen is simply wrong."""
        bot = RecordingBot()
        pi_ups = ReadableUps(battery_volts=ABOUT_TO_HALT_VOLTS)
        watch = self.build_watch(bot, pi_ups)
        await watch()

        pi_ups.reads(battery_volts=3.44, mains_present=True)
        await watch()

        self.assertEqual(
            (bot.edits, await self.lane()),
            ([(501, "🔋 <b>Pi знову живиться</b>\n\nПак заряджається.")], []),
        )

    async def test_watch_a_live_socket_after_a_goodbye_from_before_a_halt_leaves_it_standing(self):
        bot = RecordingBot()
        async with self.uow_factory() as uow:
            await uow.posted_messages.create(
                {
                    "kind": PI_PACK_WARNING_KIND,
                    "reference": PackWarning.HALTING.value,
                    "chat_id": CHAT_ID,
                    "message_id": 404,
                }
            )

        await self.build_watch(bot, ReadableUps(battery_volts=3.95, mains_present=True))()

        self.assertEqual((bot.edits, await self.lane()), ([], []))

    async def test_watch_a_hat_that_cannot_be_read_neither_warns_nor_forgets_what_was_said(self):
        bot = RecordingBot()
        pi_ups = ReadableUps(battery_volts=UNDER_AN_HOUR_VOLTS)
        await self.build_watch(bot, pi_ups)()

        await self.build_watch(bot, SilentUps())()

        self.assertEqual((len(bot.sent), bot.edits, await self.lane()), (1, [], [PackWarning.LOW.value]))

    async def test_watch_a_second_outage_after_the_first_was_cleared_warns_again(self):
        bot = RecordingBot()
        pi_ups = ReadableUps(battery_volts=UNDER_AN_HOUR_VOLTS)
        watch = self.build_watch(bot, pi_ups)
        await watch()
        pi_ups.reads(battery_volts=4.10, mains_present=True)
        await watch()

        pi_ups.reads(battery_volts=UNDER_AN_HOUR_VOLTS)
        await watch()

        self.assertEqual((len(bot.sent), await self.lane()), (2, [PackWarning.LOW.value]))
