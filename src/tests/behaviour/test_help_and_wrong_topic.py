from src.bot import messages
from src.tests.behaviour.base import BaseBehaviourTestCase
from src.tests.telegram import CHAT_ID, CHORES_TOPIC, PLANTS_TOPIC, callback_update, message_update

TRANSIT_THREAD = 41
UNREGISTERED_THREAD = 99


class HelpAndWrongTopicTestCase(BaseBehaviourTestCase):
    """
    What the bot says about itself, in the places it is read — and that it never names a command that is not there.

    a command menu that offers /add and an answer that says «ця команда працює в іншому топіку» to somebody standing
    in the right one teaches the family to stop believing the answer, which is worse than saying nothing.
    """

    async def remember_topic(self, module_name: str, message_thread_id: int) -> None:
        async with self.uow as uow:
            await uow.forum_topics.create(
                {"module_name": module_name, "chat_id": CHAT_ID, "message_thread_id": message_thread_id}
            )

    async def test_start_in_the_transit_topic_shows_only_the_transit_commands(self):
        await self.remember_topic("transit", TRANSIT_THREAD)

        await self.feed(message_update("/start", topic=TRANSIT_THREAD))

        self.assertEqual(self.session.sent_texts(), [messages.TOPIC_HELP["transit"]])

    async def test_start_in_a_topic_the_bot_does_not_own_shows_the_full_welcome(self):
        await self.feed(message_update("/start", topic=UNREGISTERED_THREAD))

        self.assertEqual(self.session.sent_texts(), [messages.WELCOME])

    async def test_help_in_the_transit_topic_names_the_russian_alias_of_bus(self):
        await self.remember_topic("transit", TRANSIT_THREAD)

        await self.feed(message_update("/help", topic=TRANSIT_THREAD))

        self.assertIn("/bus або /транспорт", self.session.sent_texts()[0])

    async def test_help_in_the_plants_topic_says_a_plain_question_is_answered(self):
        await self.remember_topic("plants", PLANTS_TOPIC)

        await self.feed(message_update("/help", topic=PLANTS_TOPIC))

        self.assertIn("«чому жовтіє листя Тігла»", self.session.sent_texts()[0])

    async def test_help_in_the_climate_topic_lists_the_climate_command(self):
        await self.remember_topic("weather", 13)

        await self.feed(message_update("/help", topic=13))

        self.assertIn("/climate — клімат удома по кімнатах", self.session.sent_texts()[0])

    async def test_add_in_the_chores_topic_says_it_does_not_exist_there_and_where_it_does(self):
        await self.remember_topic("chores", CHORES_TOPIC)

        await self.feed(message_update("/add", topic=CHORES_TOPIC))

        self.assertEqual(
            self.session.sent_texts(),
            [
                "У цьому топіку команди /add немає.\n\n"
                "<b>📋 справи</b>\n"
                "напиши, що треба зробити (з датою — «до 31.07»)\n"
                "/list — список справ\n\n"
                "/add працює тут: 🪴 рослини, 🛒 шо треба."
            ],
        )

    async def test_transport_alias_in_the_plants_topic_says_it_does_not_exist_there(self):
        await self.remember_topic("plants", PLANTS_TOPIC)

        await self.feed(message_update("/транспорт", topic=PLANTS_TOPIC))

        self.assertTrue(self.session.sent_texts()[0].endswith("/транспорт працює тут: 🚌 транспорт."))

    async def test_add_in_a_topic_the_bot_does_not_own_lists_where_commands_live(self):
        await self.feed(message_update("/add", topic=UNREGISTERED_THREAD))

        self.assertEqual(self.session.sent_texts(), [messages.WRONG_TOPIC])

    async def test_a_stale_button_points_to_help_which_works_in_every_topic(self):
        await self.feed(callback_update("plants:unknown"))

        (answer,) = self.session.calls_named("AnswerCallbackQuery")
        self.assertEqual(answer.text, "Ця кнопка вже застара 🙃 Напиши /help — там усе, що вміє цей топік.")
