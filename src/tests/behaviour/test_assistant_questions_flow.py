from src.bot.handlers.assistant import messages
from src.common.constants import CareTaskType
from src.common.domain import Actor
from src.modules.assistant.services.conversation_memory import ConversationMemory
from src.modules.assistant.use_cases.answer_question import AnswerQuestionUseCase
from src.modules.chores.commands import AddChoreCommand
from src.modules.chores.use_cases.add_chore import AddChoreUseCase
from src.modules.shopping.commands import AddShoppingItemCommand
from src.modules.shopping.use_cases.add_shopping_item import AddShoppingItemUseCase
from src.tests.behaviour.base import BaseBehaviourTestCase
from src.tests.fakes import FixedKnowledgeSource, FixedLanguageModel
from src.tests.telegram import ACTOR_ID, ACTOR_NAME, ASSISTANT_TOPIC, message_update


class AssistantQuestionsFlowTestCase(BaseBehaviourTestCase):
    """
    The assistant topic is the one with no subject of its own, so it answers from every module's record.

    «коли ми поливали Бубика» has an answer in the database, and the whole point of asking the bot rather than
    the internet is that it is the one who can read it.
    """

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.language_model = FixedLanguageModel(answer="Востаннє в понеділок.")
        self.answer_question = AnswerQuestionUseCase(
            language_model=self.language_model,
            knowledge_source=FixedKnowledgeSource("Квартира в Києві."),
            conversation_memory=ConversationMemory(),
        )
        self.actor = Actor(telegram_user_id=ACTOR_ID, display_name=ACTOR_NAME)

    async def ask(self, question: str):
        return await self.feed(
            message_update(question, update_id=9, topic=ASSISTANT_TOPIC), answer_question=self.answer_question
        )

    async def test_a_question_in_the_assistant_topic_is_answered(self):
        await self.ask("Коли поливали Бубика?")

        self.assertEqual([call.text for call in self.session.calls_named("SendMessage")], [messages.ASSISTANT_THINKING])
        self.assertEqual([call.text for call in self.session.calls_named("EditMessageText")], ["Востаннє в понеділок."])

    async def test_a_question_in_the_assistant_topic_carries_the_plants_the_chores_and_the_shopping_list(self):
        plant_id = await self.seed_plant(name="Бубик", species="Chlorophytum")
        await self.seed_care_schedule(plant_id=plant_id, task_type=CareTaskType.WATERING, interval_days=7)
        await AddChoreUseCase(uow=self.uow_factory(), actor=self.actor)(AddChoreCommand(name="Помити вікна"))
        await AddShoppingItemUseCase(uow=self.uow_factory(), actor=self.actor)(AddShoppingItemCommand(name="Олія"))

        await self.ask("Що в нас удома?")

        facts = self.language_model.system_instructions[0]
        self.assertIn("Бубик", facts)
        self.assertIn("Помити вікна", facts)
        self.assertIn("Олія", facts)
        # the household facts file is still the ground under all of it, not something the modules replace
        self.assertIn("Квартира в Києві.", facts)

    async def test_a_question_asked_with_an_empty_house_carries_only_the_facts_file(self):
        await self.ask("Що в нас удома?")

        facts = self.language_model.system_instructions[0].split("Факти про дім:\n")[1]
        self.assertEqual(facts, "Квартира в Києві.")
