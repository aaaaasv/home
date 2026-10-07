import tempfile
from datetime import timedelta
from pathlib import Path

from src.common.constants import CareTaskType
from src.modules.assistant.services.conversation_memory import ConversationMemory
from src.modules.assistant.use_cases.answer_question import AnswerQuestionUseCase
from src.tests.behaviour.base import BaseBehaviourTestCase
from src.tests.fakes import FixedKnowledgeSource, FixedLanguageModel
from src.tests.integration.base import FROZEN_NOW
from src.tests.telegram import message_update


class PlantQuestionsFlowTestCase(BaseBehaviourTestCase):
    """
    Plain text in the plants topic is a question about these plants, answered from their own record.

    the whole value is in the facts that travel with it: a general answer about ficuses is what the internet
    already gives for free.
    """

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.language_model = FixedLanguageModel(answer="Схоже на перелив.")
        self.answer_question = AnswerQuestionUseCase(
            language_model=self.language_model,
            knowledge_source=FixedKnowledgeSource("Квартира в Києві."),
            conversation_memory=ConversationMemory(),
        )
        self.photo_directory: tempfile.TemporaryDirectory | None = None

    async def ask(self, question: str):
        return await self.feed(message_update(question, update_id=9), answer_question=self.answer_question)

    async def test_a_question_in_the_plants_topic_is_answered(self):
        await self.ask("Чому жовтіє листя?")

        # the placeholder is sent, then becomes the answer in place — no second message lands in the topic
        self.assertEqual([call.text for call in self.session.calls_named("SendMessage")], ["🌱 Дивлюсь у записи…"])
        self.assertEqual([call.text for call in self.session.calls_named("EditMessageText")], ["Схоже на перелив."])

    async def test_a_question_carries_this_collection_and_its_real_watering_gaps(self):
        plant_id = await self.seed_plant(name="Тігл", species="Ficus")
        await self.seed_care_schedule(plant_id=plant_id, task_type=CareTaskType.WATERING, interval_days=7)
        await self.seed_care_event(
            plant_id=plant_id, task_type=CareTaskType.WATERING, performed_at=FROZEN_NOW - timedelta(days=8)
        )
        await self.seed_care_event(
            plant_id=plant_id, task_type=CareTaskType.WATERING, performed_at=FROZEN_NOW - timedelta(days=4)
        )

        await self.ask("Чому жовтіє листя Тігла?")

        facts = self.language_model.system_instructions[0]
        self.assertIn("Тігл", facts)
        self.assertIn("Ficus", facts)
        self.assertIn("справжні проміжки між поливами", facts)
        # the household facts file is still there — the plants are added to it, not substituted for it
        self.assertIn("Квартира в Києві.", facts)

    async def test_a_question_asked_where_no_model_is_configured_says_nothing_at_all(self):
        await self.feed(message_update("Чому жовтіє листя?", update_id=9))

        self.assertEqual(self.session.sent_texts(), [])

    async def test_a_mistyped_command_is_not_sent_to_the_model_as_a_question(self):
        await self.feed(message_update("/lst", update_id=9), answer_question=self.answer_question)

        self.assertEqual(self.language_model.conversations, [])

    async def store_photo(self, plant_id: int, contents: bytes, **overrides) -> str:
        """A stored frame that really exists on disk, the way the photo storage leaves one."""
        if self.photo_directory is None:
            self.photo_directory = tempfile.TemporaryDirectory()
            self.addCleanup(self.photo_directory.cleanup)
        path = Path(self.photo_directory.name) / f"{overrides.get('telegram_file_unique_id', 'unique-1')}.jpg"
        path.write_bytes(contents)
        await self.seed_plant_photo(plant_id=plant_id, local_path=str(path), **overrides)
        return str(path)

    async def test_a_question_naming_a_plant_carries_that_plants_own_frames(self):
        plant_id = await self.seed_plant(name="Бубик")
        await self.store_photo(plant_id, b"older-frame", telegram_file_unique_id="unique-a")
        await self.store_photo(plant_id, b"newest-frame", telegram_file_unique_id="unique-b")

        await self.ask("що з листям Бубика?")

        asked = self.language_model.conversations[0][-1]
        self.assertEqual([image.data for image in asked.images], [b"older-frame", b"newest-frame"])

    async def test_a_question_naming_a_plant_says_in_the_facts_which_frame_is_which(self):
        plant_id = await self.seed_plant(name="Бубик")
        await self.store_photo(plant_id, b"newest-frame")

        await self.ask("що з листям Бубика?")

        self.assertIn(
            "До питання додано фото з колекції, у цьому порядку:\n— Бубик, 1 липня 2026",
            self.language_model.system_instructions[0],
        )

    async def test_a_question_naming_no_plant_carries_no_frame_but_says_photos_exist(self):
        plant_id = await self.seed_plant(name="Бубик")
        await self.store_photo(plant_id, b"newest-frame")

        await self.ask("чому жовтіє листя?")

        self.assertEqual(self.language_model.conversations[0][-1].images, ())
        self.assertIn("фото: 1, останнє 2026-07-01", self.language_model.system_instructions[0])

    async def test_a_question_whose_frame_was_pruned_off_disk_is_still_answered(self):
        plant_id = await self.seed_plant(name="Бубик")
        await self.seed_plant_photo(plant_id=plant_id, local_path="/photos/gone.jpg")

        await self.ask("що з листям Бубика?")

        self.assertEqual(self.language_model.conversations[0][-1].images, ())
        self.assertEqual([call.text for call in self.session.calls_named("EditMessageText")], ["Схоже на перелив."])
