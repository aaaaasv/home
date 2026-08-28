from src.bot.handlers.plants import messages
from src.tests.behaviour.base import BaseBehaviourTestCase
from src.tests.telegram import callback_update, message_update


class AddPlantFlowTestCase(BaseBehaviourTestCase):
    """
    The whole /add wizard, driven the way a person drives it.

    every user-visible bug this month lived in this layer, and until now nothing here was executed by a test:
    a handler could take a parameter that is never injected and the suite stayed green.
    """

    async def test_add_plant_asks_for_a_name_first(self):
        await self.feed(message_update("/add"))

        self.assertEqual(self.session.sent_texts(), [messages.ADD_PLANT_ASK_NAME])

    async def test_add_plant_asks_for_a_photo_once_it_has_a_name(self):
        await self.feed(message_update("/add", update_id=1))

        await self.feed(message_update("Монстера", update_id=2))

        self.assertEqual(self.session.sent_texts()[-1], messages.ADD_PLANT_ASK_PHOTO)

    async def test_add_plant_skipping_the_photo_goes_straight_to_the_watering_rhythm(self):
        await self.feed(message_update("/add", update_id=1))
        await self.feed(message_update("Монстера", update_id=2))

        await self.feed(message_update("/skip", update_id=3))

        self.assertEqual(self.session.sent_texts()[-1], messages.ADD_PLANT_ASK_INTERVAL)

    async def test_add_plant_answering_the_rhythm_creates_the_plant_and_shows_its_card(self):
        await self.feed(message_update("/add", update_id=1))
        await self.feed(message_update("Монстера", update_id=2))
        await self.feed(message_update("/skip", update_id=3))

        await self.feed(callback_update("new_interval:7", update_id=4))

        async with self.uow as uow:
            plants = await uow.plants.list_active()
        self.assertEqual([plant.name for plant in plants], ["Монстера"])
        self.assertIn("Монстера", self.session.sent_texts()[-1])

    async def test_add_plant_records_whoever_typed_the_name_as_a_family_member(self):
        await self.feed(message_update("/add", update_id=1))

        await self.feed(message_update("Монстера", update_id=2))

        async with self.uow as uow:
            members = await uow.family_members.list_all()
        self.assertEqual([member.display_name for member in members], ["Тест"])

    async def test_cancel_abandons_the_flow_so_the_next_plain_text_is_not_taken_as_a_name(self):
        await self.feed(message_update("/add", update_id=1))
        await self.feed(message_update("/cancel", update_id=2))
        self.session.calls.clear()

        await self.feed(message_update("Монстера", update_id=3))

        # a cancelled wizard does not take the next word as a name; without a model configured the question
        # handler that now owns plain text here says nothing either
        self.assertEqual(self.session.sent_texts(), [])
        async with self.uow as uow:
            self.assertEqual(await uow.plants.list_active(), [])
