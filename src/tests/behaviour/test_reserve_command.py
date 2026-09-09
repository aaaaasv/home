from src.bot.handlers.power.messages import POWER_RESERVE_UNAVAILABLE
from src.tests.behaviour.base import BaseBehaviourTestCase
from src.tests.telegram import POWER_TOPIC, message_update


class RecordingReserveBoard:
    """Counts what the command asked of the board; how the board itself draws has its own tests"""

    def __init__(self) -> None:
        self.posts = 0

    async def post(self, *args, **kwargs) -> None:
        self.posts += 1


class ReserveCommandTestCase(BaseBehaviourTestCase):
    """
    /reserve exists so nobody has to scroll for a board that may be two days up the topic.

    it is fed through the real dispatcher because that is the only thing that proves the handler's board is
    actually injected — a parameter nothing supplies would leave every other test in the suite green.
    """

    async def test_reserve_in_the_power_topic_moves_the_board_to_the_bottom(self):
        reserve_board = RecordingReserveBoard()

        await self.feed(message_update("/reserve", topic=POWER_TOPIC), reserve_board=reserve_board)

        self.assertEqual(reserve_board.posts, 1)

    async def test_reserve_without_a_board_configured_says_so_instead_of_going_silent(self):
        await self.feed(message_update("/reserve", topic=POWER_TOPIC), reserve_board=None)

        self.assertEqual(self.session.sent_texts(), [POWER_RESERVE_UNAVAILABLE])
