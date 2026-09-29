from aiogram.types import ForceReply

from src.tests.behaviour.base import BaseBehaviourTestCase
from src.tests.telegram import PLACES_TOPIC, callback_update, message_update


class PlacesFlowTestCase(BaseBehaviourTestCase):
    """A button pressed on a place's menu, all the way through to the record it changes."""

    async def add_museum(self) -> int:
        await self.feed(message_update("музей", update_id=1, topic=PLACES_TOPIC))
        async with self.uow as uow:
            places = await uow.places.list_all()
        return places[0].id

    async def test_rename_button_asks_for_the_new_name_with_a_force_reply_and_the_answer_renames_the_place(self):
        place_id = await self.add_museum()
        self.session.calls.clear()

        await self.feed(callback_update(f"place:rename:{place_id}", update_id=2, topic=PLACES_TOPIC))

        prompt = self.session.calls_named("SendMessage")[-1]
        self.assertEqual(prompt.reply_markup, ForceReply(selective=True, input_field_placeholder="нова назва"))
        await self.feed(message_update("галерея", update_id=3, topic=PLACES_TOPIC))
        async with self.uow as uow:
            places = await uow.places.list_all()
        self.assertEqual([place.name for place in places], ["галерея"])
