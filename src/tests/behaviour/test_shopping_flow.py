from src.bot.handlers.shopping import messages
from src.tests.behaviour.base import BaseBehaviourTestCase
from src.tests.telegram import SHOPPING_TOPIC, callback_update, message_update


class ShoppingFlowTestCase(BaseBehaviourTestCase):
    """A button pressed on a card, all the way through to the record it changes and the board it redraws."""

    async def add_bread(self) -> int:
        await self.feed(message_update("/add хліб", update_id=1, topic=SHOPPING_TOPIC))
        async with self.uow as uow:
            items = await uow.shopping_items.list_unbought()
        return items[0].id

    async def test_add_by_command_puts_the_item_on_the_list(self):
        await self.feed(message_update("/add хліб", topic=SHOPPING_TOPIC))

        async with self.uow as uow:
            items = await uow.shopping_items.list_unbought()
        self.assertEqual([item.name for item in items], ["хліб"])

    async def test_buying_an_item_marks_it_bought_and_redraws_the_board(self):
        item_id = await self.add_bread()
        refreshes_before = self.shopping_list_board.refreshed

        await self.feed(callback_update(f"shop:buy:{item_id}", update_id=2))

        async with self.uow as uow:
            remaining = await uow.shopping_items.list_unbought()
        self.assertEqual(remaining, [])
        self.assertEqual(self.shopping_list_board.refreshed - refreshes_before, 1)

    async def test_buying_an_item_answers_the_tap_with_a_toast_rather_than_a_message(self):
        item_id = await self.add_bread()
        self.session.calls.clear()

        await self.feed(callback_update(f"shop:buy:{item_id}", update_id=2))

        answered = self.session.calls_named("AnswerCallbackQuery")
        self.assertEqual([call.text for call in answered], [messages.SHOPPING_BOUGHT_TOAST])
        self.assertEqual(self.session.calls_named("SendMessage"), [])
