from datetime import timedelta

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageText

from src.bot.handlers.transit.board import TransitBoard
from src.bot.handlers.transit.messages import TRANSIT_LOOKING
from src.bot.services.posted_message_tracker import TRANSIT_CARD_KIND
from src.infrastructure.db.uow import UnitOfWork
from src.modules.transit.domain import RouteArrival, RouteVehicleKind, TransitReport, TransitReportStatus, WatchedRoute
from src.tests.fakes import RecordingBot, StubForumTopic
from src.tests.integration.base import KYIV, BaseIntegrationTestCase

CHAT_ID = -1000
THREAD_ID = 100
# the card body the canned report renders to, shared by every in-place assertion below (the footer carries the clock)
CARD_BODY = "найближчий: 🚎 3 за ~4 хв (~1.1 км) · 🚎 9К поки не видно"


class StubComposeTransitReport:
    """Stands in for the real use case another track fills — hands back a canned report and counts the polls"""

    def __init__(self, report: TransitReport):
        self.report = report
        self.calls = 0

    async def __call__(self) -> TransitReport:
        self.calls += 1
        return self.report


class ExpiredEditBot(RecordingBot):
    """Raises "message can't be edited" on its first edit, mimicking a card that has aged past the 48h window"""

    def __init__(self, first_message_id: int = 500):
        super().__init__(first_message_id=first_message_id)
        self.edit_attempts = 0

    async def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        self.edit_attempts += 1
        if self.edit_attempts == 1:
            raise TelegramBadRequest(
                method=EditMessageText(chat_id=chat_id, message_id=message_id, text=text),
                message="message can't be edited",
            )
        await super().edit_message_text(chat_id, message_id, text, reply_markup)


def build_arrivals_report() -> TransitReport:
    return TransitReport(
        status=TransitReportStatus.ARRIVALS,
        arrivals=[
            RouteArrival(
                route=WatchedRoute(route_id="2_30", short_name="3", vehicle_kind=RouteVehicleKind.TROLLEYBUS),
                eta_minutes=4,
                distance_meters=1100.0,
            ),
            RouteArrival(
                route=WatchedRoute(route_id="2_842", short_name="9К", vehicle_kind=RouteVehicleKind.TROLLEYBUS),
                eta_minutes=None,
                distance_meters=None,
            ),
        ],
    )


class TransitBoardTestCase(BaseIntegrationTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.bot = RecordingBot()
        self.compose = StubComposeTransitReport(build_arrivals_report())

    def uow_factory(self) -> UnitOfWork:
        return UnitOfWork(session_factory=self.session_factory)

    def build_board(
        self,
        bot: RecordingBot | None = None,
        refresh_interval: timedelta = timedelta(seconds=60),
        refresh_window: timedelta = timedelta(minutes=5),
    ) -> TransitBoard:
        board = TransitBoard(
            bot=bot if bot is not None else self.bot,
            chat_id=CHAT_ID,
            transit_topic=StubForumTopic(THREAD_ID),
            uow_factory=self.uow_factory,
            compose_transit_report=self.compose,
            timezone=KYIV,
            refresh_interval=refresh_interval,
            refresh_window=refresh_window,
        )
        self.addAsyncCleanup(board.stop)
        return board

    async def seed_card(self, message_id: int) -> None:
        async with self.uow_factory() as uow:
            await uow.posted_messages.create(
                {"kind": TRANSIT_CARD_KIND, "chat_id": CHAT_ID, "message_id": message_id, "reference": None}
            )

    async def list_cards(self) -> list:
        async with self.uow_factory() as uow:
            return await uow.posted_messages.list_by_kind(TRANSIT_CARD_KIND)

    async def test_post_replaces_the_previous_card_and_remembers_the_new_one(self):
        await self.seed_card(message_id=400)
        board = self.build_board()

        await board.post()

        placeholder = self.bot.sent[0]
        self.assertEqual(self.bot.deleted, [400])
        self.assertEqual(len(self.bot.sent), 1)
        self.assertEqual(placeholder["text"], TRANSIT_LOOKING)
        self.assertEqual(placeholder["message_thread_id"], THREAD_ID)
        self.assertEqual(placeholder["silent"], True)
        self.assertEqual(len(self.bot.edited), 1)
        self.assertEqual(self.bot.edited[0]["message_id"], placeholder["message_id"])
        cards = await self.list_cards()
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].message_id, placeholder["message_id"])

    async def test_refresh_once_edits_the_card_in_place_silently(self):
        board = self.build_board()
        await board.post()
        card_message_id = self.bot.sent[0]["message_id"]

        await board._refresh_once()

        self.assertEqual(len(self.bot.sent), 1)
        self.assertEqual(len(self.bot.edited), 2)
        self.assertEqual(self.bot.edited[-1]["message_id"], card_message_id)
        body, footer = self.bot.edited[-1]["text"].split("\n\n")
        self.assertEqual(body, CARD_BODY)
        self.assertTrue(footer.startswith("<i>оновлюється · станом на "))
        self.assertTrue(footer.endswith("</i>"))

    async def test_refresh_once_reposts_the_card_when_the_edit_window_has_expired(self):
        bot = ExpiredEditBot()
        await self.seed_card(message_id=400)
        board = self.build_board(bot=bot)

        reposted = await board._refresh_once()

        self.assertTrue(reposted)
        self.assertEqual(bot.deleted, [400])
        self.assertEqual(len(bot.sent), 1)
        self.assertEqual(bot.sent[0]["text"], TRANSIT_LOOKING)
        self.assertEqual(len(bot.edited), 1)
        self.assertEqual(bot.edited[0]["message_id"], bot.sent[0]["message_id"])
        cards = await self.list_cards()
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].message_id, bot.sent[0]["message_id"])

    async def test_freeze_rewrites_the_footer_and_stops_the_window(self):
        board = self.build_board(refresh_interval=timedelta(seconds=0), refresh_window=timedelta(seconds=0))
        await board.post()
        window_task = board._refresh_task

        await window_task

        self.assertTrue(window_task.done())
        self.assertIsNone(board._refresh_task)
        self.assertEqual(len(self.bot.edited), 2)
        live_footer = self.bot.edited[0]["text"].split("\n\n")[1]
        self.assertTrue(live_footer.startswith("<i>оновлюється · станом на "))
        frozen_body, frozen_footer = self.bot.edited[-1]["text"].split("\n\n")
        self.assertEqual(frozen_body, CARD_BODY)
        self.assertTrue(frozen_footer.startswith("<i>станом на "))
        self.assertTrue(frozen_footer.endswith(" · 🔄 щоб оновити</i>"))

    async def test_resume_restarts_the_refresh_window_on_a_frozen_card(self):
        board = self.build_board()
        await board.post()
        card_message_id = self.bot.sent[0]["message_id"]
        await board.stop()
        await board._freeze()
        self.assertIsNone(board._refresh_task)

        await board.resume()

        self.assertIsNotNone(board._refresh_task)
        self.assertFalse(board._refresh_task.done())
        self.assertEqual(len(self.bot.sent), 1)
        self.assertEqual(self.bot.edited[-1]["message_id"], card_message_id)
        live_footer = self.bot.edited[-1]["text"].split("\n\n")[1]
        self.assertTrue(live_footer.startswith("<i>оновлюється · станом на "))
