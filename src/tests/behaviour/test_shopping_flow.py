from aiogram.types import ForceReply

from src.bot.handlers.shopping import messages
from src.modules.shopping.constants import ShoppingHorizon
from src.tests.behaviour.base import BaseBehaviourTestCase
from src.tests.fakes import ScriptedPriceSource
from src.tests.telegram import ACTOR_ID, SHOPPING_TOPIC, callback_update, message_update

HOTLINE_URL = "https://hotline.ua/ua/mobile-x/dyson-v15/"


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

    async def test_add_by_bare_command_asks_what_to_buy_and_opens_the_input_field_for_the_asker_only(self):
        await self.feed(message_update("/add", topic=SHOPPING_TOPIC))

        prompt = self.session.calls_named("SendMessage")[-1]
        self.assertEqual(prompt.text, f'<a href="tg://user?id={ACTOR_ID}">\u200b</a>{messages.SHOPPING_ASK_NEW_ITEM}')
        self.assertEqual(prompt.reply_markup, ForceReply(selective=True, input_field_placeholder="що купити"))
        self.assertTrue(prompt.disable_notification)

    async def test_add_by_bare_command_then_text_puts_the_item_on_the_list_and_sweeps_the_prompt(self):
        await self.feed(message_update("/add", update_id=1, topic=SHOPPING_TOPIC))
        prompt_message_id = self.session.next_message_id
        self.session.calls.clear()

        await self.feed(message_update("хліб", update_id=2, topic=SHOPPING_TOPIC))

        async with self.uow as uow:
            items = await uow.shopping_items.list_unbought()
        self.assertEqual([(item.name, item.horizon) for item in items], [("хліб", ShoppingHorizon.NOW)])
        deleted_message_ids = [call.message_id for call in self.session.calls_named("DeleteMessage")]
        self.assertEqual(deleted_message_ids, [2, prompt_message_id])

    async def test_add_by_bare_later_command_then_text_puts_the_item_on_the_someday_list(self):
        await self.feed(message_update("/later", update_id=1, topic=SHOPPING_TOPIC))

        await self.feed(message_update("пилосос", update_id=2, topic=SHOPPING_TOPIC))

        async with self.uow as uow:
            items = await uow.shopping_items.list_unbought()
        self.assertEqual([(item.name, item.horizon) for item in items], [("пилосос", ShoppingHorizon.LATER)])

    async def test_add_by_bare_later_command_asks_what_to_buy_someday(self):
        await self.feed(message_update("/later", topic=SHOPPING_TOPIC))

        prompt = self.session.calls_named("SendMessage")[-1]
        self.assertIn(messages.SHOPPING_ASK_LATER_ITEM, prompt.text)
        self.assertEqual(prompt.reply_markup.input_field_placeholder, "що купити колись")

    async def test_add_after_bare_command_with_a_too_long_name_keeps_waiting_for_a_shorter_one(self):
        await self.feed(message_update("/add", update_id=1, topic=SHOPPING_TOPIC))
        await self.feed(message_update("х" * 129, update_id=2, topic=SHOPPING_TOPIC))

        await self.feed(message_update("хліб", update_id=3, topic=SHOPPING_TOPIC))

        async with self.uow as uow:
            items = await uow.shopping_items.list_unbought()
        self.assertEqual([item.name for item in items], ["хліб"])
        self.assertIn(messages.SHOPPING_NAME_TOO_LONG, self.session.sent_texts())

    async def test_track_by_bare_command_asks_for_the_link_and_opens_the_input_field_for_the_asker_only(self):
        await self.feed(message_update("/track", topic=SHOPPING_TOPIC))

        prompt = self.session.calls_named("SendMessage")[-1]
        self.assertEqual(prompt.text, f'<a href="tg://user?id={ACTOR_ID}">\u200b</a>{messages.TRACK_ASK_LINK}')
        self.assertEqual(
            prompt.reply_markup, ForceReply(selective=True, input_field_placeholder="посилання з hotline.ua")
        )

    async def test_track_by_bare_command_then_a_hotline_link_puts_a_tracked_item_on_the_list(self):
        price_source = ScriptedPriceSource({HOTLINE_URL: [21999]}, name="Пилосос Dyson")
        await self.feed(message_update("/track", update_id=1, topic=SHOPPING_TOPIC), price_source=price_source)

        await self.feed(message_update(HOTLINE_URL, update_id=2, topic=SHOPPING_TOPIC), price_source=price_source)

        async with self.uow as uow:
            items = await uow.shopping_items.list_unbought()
        self.assertEqual([(item.name, item.hotline_url) for item in items], [("Пилосос Dyson", HOTLINE_URL)])

    async def test_track_by_bare_command_then_a_foreign_link_refuses_it_and_keeps_waiting(self):
        price_source = ScriptedPriceSource({HOTLINE_URL: [21999]}, name="Пилосос Dyson")
        await self.feed(message_update("/track", update_id=1, topic=SHOPPING_TOPIC), price_source=price_source)
        await self.feed(
            message_update("https://example.com/a", update_id=2, topic=SHOPPING_TOPIC), price_source=price_source
        )

        await self.feed(message_update(HOTLINE_URL, update_id=3, topic=SHOPPING_TOPIC), price_source=price_source)

        async with self.uow as uow:
            items = await uow.shopping_items.list_unbought()
        self.assertEqual([item.name for item in items], ["Пилосос Dyson"])
        self.assertIn(messages.TRACK_NOT_HOTLINE, self.session.sent_texts())

    async def test_rename_button_asks_for_the_new_name_with_a_force_reply_and_the_answer_renames_the_item(self):
        item_id = await self.add_bread()
        self.session.calls.clear()
        rename = f"shop:rename:{item_id}"

        await self.feed(callback_update(rename, update_id=2, topic=SHOPPING_TOPIC))

        prompt = self.session.calls_named("SendMessage")[-1]
        self.assertEqual(prompt.reply_markup, ForceReply(selective=True, input_field_placeholder="нова назва"))
        await self.feed(message_update("батон", update_id=3, topic=SHOPPING_TOPIC))
        async with self.uow as uow:
            items = await uow.shopping_items.list_unbought()
        self.assertEqual([item.name for item in items], ["батон"])

    async def test_note_button_asks_for_the_note_with_a_force_reply_that_explains_the_dash(self):
        item_id = await self.add_bread()

        await self.feed(callback_update(f"shop:note:{item_id}", update_id=2, topic=SHOPPING_TOPIC))

        prompt = self.session.calls_named("SendMessage")[-1]
        self.assertEqual(
            prompt.reply_markup, ForceReply(selective=True, input_field_placeholder="опис, або «-» щоб прибрати")
        )

    async def test_track_button_asks_for_the_link_with_a_force_reply(self):
        item_id = await self.add_bread()

        await self.feed(callback_update(f"shop:track:{item_id}", update_id=2, topic=SHOPPING_TOPIC))

        prompt = self.session.calls_named("SendMessage")[-1]
        self.assertEqual(
            prompt.reply_markup, ForceReply(selective=True, input_field_placeholder="посилання з hotline.ua")
        )
