from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.bot.handlers.power.board import PowerBoard
from src.bot.services.posted_message_tracker import POWER_BOARD_KIND
from src.infrastructure.db.uow import UnitOfWork
from src.modules.power.domain import (
    DeclaredSupply,
    GridState,
    OutageInterval,
    OutageOutlook,
    OutageSchedule,
    OutageScheduleStatus,
    Reserve,
    ReserveLayer,
    ReserveRow,
    ReserveStanding,
)
from src.tests.fakes import StubForumTopic
from src.tests.integration.base import BaseIntegrationTestCase

CHAT_ID = -1001234567890
KYIV = ZoneInfo("Europe/Kyiv")


class RecordingBoardBot:
    """Records what the board asked Telegram to do."""

    def __init__(self):
        self.sent: list[str] = []
        self.markups: list = []
        self.edited: list[tuple[int, str]] = []
        self.deleted: list[int] = []

    async def send_message(self, chat_id, message_thread_id, text, reply_markup, disable_notification):
        self.sent.append(text)
        self.markups.append(reply_markup)

        class Chat:
            id = chat_id

        class Sent:
            chat = Chat()
            message_id = 700 + len(self.sent)

        return Sent()

    async def edit_message_text(self, chat_id, message_id, text, reply_markup):
        self.edited.append((message_id, text))

    async def delete_message(self, chat_id, message_id):
        self.deleted.append(message_id)


class StubScheduleProvider:
    def __init__(self, outlook: OutageOutlook | None = None):
        self.outlook = outlook
        self.fetches = 0

    async def fetch(self) -> OutageOutlook | None:
        self.fetches += 1
        return self.outlook

    async def fetch_today(self) -> OutageSchedule | None:
        raise AssertionError("the board must read both days, not today alone")


def build_schedule(day: date, *intervals: OutageInterval) -> OutageSchedule:
    return OutageSchedule(
        day=day,
        status=OutageScheduleStatus.SCHEDULE_APPLIES,
        off_intervals=intervals,
        updated_on=None,
    )


class PowerBoardScheduleHalfTestCase(BaseIntegrationTestCase):
    """
    The schedule half of the one board in ⚡ світло, in a flat whose reserve cannot be read at all.

    that is the honest way to test it: with no hat and no station there are no layers to draw, so whatever
    the board does here it does because of the hours yasno published.
    """

    def uow_factory(self) -> UnitOfWork:
        return UnitOfWork(session_factory=self.session_factory)

    def build_board(self, bot, provider: StubScheduleProvider) -> PowerBoard:
        return PowerBoard(
            bot=bot,
            chat_id=CHAT_ID,
            power_topic=StubForumTopic(),
            uow_factory=self.uow_factory,
            timezone=KYIV,
            schedule_provider=provider,
        )

    async def build_board_knowing(self, bot, outlook: OutageOutlook | None) -> PowerBoard:
        """The board draws what it was last told, so a test has to tell it the way the poll job does."""
        board = self.build_board(bot, StubScheduleProvider(outlook))
        await board.read_outlook()
        return board

    async def remembered_message_ids(self) -> list[int]:
        async with self.uow_factory() as uow:
            return [posted.message_id for posted in await uow.posted_messages.list_by_kind(POWER_BOARD_KIND)]

    def tomorrow_only_outlook(self) -> OutageOutlook:
        """An outlook whose only intervals are tomorrow's — ahead of any wall clock the test may run at."""
        today = datetime.now(KYIV).date()
        return OutageOutlook(
            today=build_schedule(today),
            tomorrow=build_schedule(today + timedelta(days=1), OutageInterval(900, 1110)),
        )

    def spent_day_outlook(self) -> OutageOutlook:
        """A day that is already over and nothing published for tomorrow — behind any wall clock."""
        return OutageOutlook(today=build_schedule(date(2026, 1, 2), OutageInterval(0, 210)), tomorrow=None)

    async def test_post_with_tomorrow_planned_shows_both_day_headings(self):
        bot = RecordingBoardBot()

        board = await self.build_board_knowing(bot, self.tomorrow_only_outlook())

        await board.post()

        self.assertEqual(len(bot.sent), 1)
        self.assertIn("<b>Завтра</b>", bot.sent[0])
        self.assertIn("🕯 15:00–18:30", bot.sent[0])
        self.assertEqual(await self.remembered_message_ids(), [701])

    async def test_post_with_a_day_that_has_no_outages_leaves_that_day_out(self):
        bot = RecordingBoardBot()

        board = await self.build_board_knowing(bot, self.tomorrow_only_outlook())

        await board.post()

        self.assertNotIn("<b>Сьогодні</b>", bot.sent[0])

    async def test_post_during_emergency_shutdowns_with_no_hours_still_puts_up_the_banner(self):
        """The board used to vanish at exactly the moment the published schedule stopped applying."""
        bot = RecordingBoardBot()
        today = datetime.now(KYIV).date()
        outlook = OutageOutlook(
            today=OutageSchedule(
                day=today,
                status=OutageScheduleStatus.EMERGENCY_SHUTDOWNS,
                off_intervals=(),
                updated_on=None,
            ),
            tomorrow=None,
        )

        board = await self.build_board_knowing(bot, outlook)

        await board.post()

        self.assertEqual(len(bot.sent), 1)
        self.assertIn("🚨 <b>Аварійні відключення</b>", bot.sent[0])
        self.assertEqual(await self.remembered_message_ids(), [701])

    async def test_post_with_every_interval_spent_and_no_tomorrow_says_nothing(self):
        bot = RecordingBoardBot()

        board = await self.build_board_knowing(bot, self.spent_day_outlook())

        await board.post()

        self.assertEqual(bot.sent, [])
        self.assertEqual(await self.remembered_message_ids(), [])

    async def test_post_with_nothing_published_and_no_reserve_to_draw_says_nothing(self):
        bot = RecordingBoardBot()

        board = await self.build_board_knowing(bot, None)

        await board.post()

        self.assertEqual(bot.sent, [])
        self.assertEqual(await self.remembered_message_ids(), [])

    async def test_refresh_with_no_board_yet_returns_false_and_sends_nothing(self):
        bot = RecordingBoardBot()
        provider = StubScheduleProvider(self.tomorrow_only_outlook())

        refreshed = await self.build_board(bot, provider).refresh()

        self.assertFalse(refreshed)
        self.assertEqual(bot.sent, [])
        self.assertEqual(provider.fetches, 0)

    async def test_refresh_with_a_standing_board_edits_it_in_place(self):
        bot = RecordingBoardBot()
        board = await self.build_board_knowing(bot, self.tomorrow_only_outlook())
        await board.post()

        refreshed = await board.refresh()

        self.assertTrue(refreshed)
        self.assertEqual(len(bot.edited), 1)
        self.assertEqual(bot.edited[0][0], 701)
        self.assertIn("<b>Завтра</b>", bot.edited[0][1])

    async def test_refresh_once_the_day_is_spent_takes_the_board_down(self):
        bot = RecordingBoardBot()
        board = await self.build_board_knowing(bot, self.tomorrow_only_outlook())
        await board.post()

        refreshed = await (await self.build_board_knowing(bot, self.spent_day_outlook())).refresh()

        self.assertTrue(refreshed)
        self.assertEqual(bot.deleted, [701])
        self.assertEqual(await self.remembered_message_ids(), [])


class StubReserveReadout:
    def __init__(self, reserve: Reserve | None):
        self.reserve = reserve
        self.reads = 0

    async def compose(self) -> Reserve | None:
        self.reads += 1
        return self.reserve


ON_BATTERY = Reserve(
    grid=GridState.ON_BATTERY,
    rows=(
        ReserveRow(
            layer=ReserveLayer.STATION,
            standing=ReserveStanding.HOLDING,
            charge_percent=82,
            remaining=timedelta(hours=2),
        ),
        ReserveRow(
            layer=ReserveLayer.ROUTER, standing=ReserveStanding.HOLDING_UNMEASURED, holding_for=timedelta(minutes=40)
        ),
    ),
    on_battery_for=timedelta(minutes=40),
)


class PowerBoardBothHalvesTestCase(BaseIntegrationTestCase):
    """
    One card, two halves — which is the whole point of merging the two boards that used to stand here.

    the reserve goes on top and never runs out of something to say, so unlike the old schedule board this
    card does not come and go with the published hours; it is only ever reposted, never deleted.
    """

    def uow_factory(self) -> UnitOfWork:
        return UnitOfWork(session_factory=self.session_factory)

    async def build_board(self, bot, reserve: Reserve | None, outlook: OutageOutlook | None) -> PowerBoard:
        board = PowerBoard(
            bot=bot,
            chat_id=CHAT_ID,
            power_topic=StubForumTopic(),
            uow_factory=self.uow_factory,
            timezone=KYIV,
            reserve_readout=StubReserveReadout(reserve),
            schedule_provider=StubScheduleProvider(outlook),
        )
        await board.read_outlook()
        return board

    def tomorrow_only_outlook(self) -> OutageOutlook:
        today = datetime.now(KYIV).date()
        return OutageOutlook(
            today=build_schedule(today),
            tomorrow=build_schedule(today + timedelta(days=1), OutageInterval(900, 1110)),
        )

    async def remembered_message_ids(self) -> list[int]:
        async with self.uow_factory() as uow:
            return [posted.message_id for posted in await uow.posted_messages.list_by_kind(POWER_BOARD_KIND)]

    async def test_post_with_both_halves_puts_the_reserve_over_the_schedule_under_one_as_of(self):
        bot = RecordingBoardBot()
        board = await self.build_board(bot, ON_BATTERY, self.tomorrow_only_outlook())

        await board.post()

        self.assertEqual(
            bot.sent,
            [
                "🕯 <b>Резерв</b> — на батареї 40 хв\n"
                "\n"
                "⚡ Delta 2 — 82% · лишилось ~2 год\n"
                "📡 Роутер — на батареї 40 хв\n"
                "\n"
                "🗓 <b>Графік відключень</b>\n"
                "\n"
                "<b>Завтра</b>\n"
                "🕯 15:00–18:30\n"
                "\n"
                f"<i>станом на {datetime.now(KYIV):%H:%M}</i>"
            ],
        )

    async def test_post_on_a_day_with_nothing_published_still_puts_the_reserve_up(self):
        """The half the family opens the topic for during a blackout is the one yasno knows nothing about."""
        bot = RecordingBoardBot()
        board = await self.build_board(bot, ON_BATTERY, None)

        await board.post()

        self.assertEqual(len(bot.sent), 1)
        self.assertIn("🕯 <b>Резерв</b> — на батареї 40 хв", bot.sent[0])
        self.assertNotIn("🗓", bot.sent[0])

    async def test_refresh_once_the_published_hours_are_spent_keeps_the_board_standing(self):
        bot = RecordingBoardBot()
        board = await self.build_board(bot, ON_BATTERY, self.tomorrow_only_outlook())
        await board.post()
        spent = OutageOutlook(today=build_schedule(date(2026, 1, 2), OutageInterval(0, 210)), tomorrow=None)
        board.remember(spent)

        refreshed = await board.refresh()

        self.assertTrue(refreshed)
        self.assertEqual(bot.deleted, [])
        self.assertEqual(await self.remembered_message_ids(), [701])


ON_THE_STATION = Reserve(
    grid=GridState.ON_BATTERY,
    rows=(ReserveRow(layer=ReserveLayer.PI, standing=ReserveStanding.HOLDING_UNMEASURED, charge_percent=70),),
    on_battery_for=timedelta(hours=2),
    declared_supply=DeclaredSupply.STATION,
)


class PowerBoardSupplyTestCase(BaseIntegrationTestCase):
    """
    The board is the one place the family can always reach, so it is where the station mark lives.

    the card that announced «світло є» carries the same correction, but only until the next message
    buries it — and «я перемкнувся назад» is said ten minutes later, not nineteen seconds later.
    """

    def uow_factory(self) -> UnitOfWork:
        return UnitOfWork(session_factory=self.session_factory)

    async def build_board(self, bot, reserve: Reserve) -> PowerBoard:
        return PowerBoard(
            bot=bot,
            chat_id=CHAT_ID,
            power_topic=StubForumTopic(),
            uow_factory=self.uow_factory,
            timezone=KYIV,
            reserve_readout=StubReserveReadout(reserve),
        )

    async def test_post_while_the_station_is_declared_says_so_in_words(self):
        bot = RecordingBoardBot()

        await (await self.build_board(bot, ON_THE_STATION)).post()

        self.assertIn("У розетці Pi — Delta 2, тому про місто тут нічого немає", bot.sent[0])

    async def test_post_while_the_station_is_declared_offers_the_way_back(self):
        bot = RecordingBoardBot()
        board = await self.build_board(bot, ON_THE_STATION)

        await board.post()

        self.assertEqual(
            [button.text for button in bot.markups[0].inline_keyboard[0]], ["Оновити", "Pi знову в мережі"]
        )

    async def test_post_on_the_grid_offers_the_mark_instead(self):
        bot = RecordingBoardBot()
        board = await self.build_board(bot, ON_BATTERY)

        await board.post()

        self.assertEqual(
            [button.text for button in bot.markups[0].inline_keyboard[0]], ["Оновити", "Перекинув на Delta 2"]
        )
