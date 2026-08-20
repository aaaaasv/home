import unittest
from datetime import datetime, timedelta, timezone

from src.modules.assistant.services.conversation_memory import ConversationMemory
from src.modules.assistant.services.language_model import (
    MODEL_ROLE,
    USER_ROLE,
    ConversationTurn,
    ImageAttachment,
    QuotaExhausted,
)
from src.modules.assistant.use_cases.answer_question import GROUNDING_INSTRUCTION, AnswerQuestionUseCase
from src.tests.fakes import ExhaustedLanguageModel, FixedKnowledgeSource, FixedLanguageModel

ASSISTANT_TOPIC_ID = 205
MORNING = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)


class AnswerQuestionTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_answer_question_grounds_the_system_instruction_in_the_facts_and_returns_the_model_answer(self):
        language_model = FixedLanguageModel("Останній потяг о ~22:45.")
        knowledge_source = FixedKnowledgeSource("Метро Вокзальна: останній потяг ~22:45.")
        answer_question = AnswerQuestionUseCase(language_model, knowledge_source, ConversationMemory())

        answer = await answer_question("коли останнє метро?", conversation_id=ASSISTANT_TOPIC_ID, asked_at=MORNING)

        self.assertEqual(answer, "Останній потяг о ~22:45.")
        self.assertEqual(
            language_model.system_instructions,
            [f"{GROUNDING_INSTRUCTION}\n\nФакти про дім:\nМетро Вокзальна: останній потяг ~22:45."],
        )
        self.assertEqual(language_model.conversations, [[ConversationTurn(role=USER_ROLE, text="коли останнє метро?")]])

    async def test_answer_question_passes_the_photo_to_the_model(self):
        language_model = FixedLanguageModel("Схоже на здоровий плющ.")
        image = ImageAttachment(data=b"jpeg-bytes")
        answer_question = AnswerQuestionUseCase(language_model, FixedKnowledgeSource("факти"), ConversationMemory())

        answer = await answer_question("що це?", conversation_id=ASSISTANT_TOPIC_ID, asked_at=MORNING, images=[image])

        self.assertEqual(answer, "Схоже на здоровий плющ.")
        self.assertEqual(
            language_model.conversations, [[ConversationTurn(role=USER_ROLE, text="що це?", images=(image,))]]
        )

    async def test_answer_question_returns_none_when_the_model_is_unreachable(self):
        language_model = FixedLanguageModel(None)
        answer_question = AnswerQuestionUseCase(
            language_model, FixedKnowledgeSource("будь-які факти"), ConversationMemory()
        )

        answer = await answer_question("питання", conversation_id=ASSISTANT_TOPIC_ID, asked_at=MORNING)

        self.assertIsNone(answer)


class AnswerQuestionWithMemoryTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.language_model = FixedLanguageModel("Плющ поливають раз на тиждень.", ["Взимку — раз на два тижні."])
        self.answer_question = AnswerQuestionUseCase(
            self.language_model, FixedKnowledgeSource("Плющ стоїть на кухні."), ConversationMemory()
        )

    async def test_answer_question_after_an_earlier_question_carries_the_previous_exchange(self):
        await self.answer_question("як часто поливати плющ?", conversation_id=ASSISTANT_TOPIC_ID, asked_at=MORNING)

        answer = await self.answer_question(
            "а взимку?", conversation_id=ASSISTANT_TOPIC_ID, asked_at=MORNING + timedelta(minutes=2)
        )

        self.assertEqual(answer, "Взимку — раз на два тижні.")
        self.assertEqual(
            self.language_model.conversations[1],
            [
                ConversationTurn(role=USER_ROLE, text="як часто поливати плющ?"),
                ConversationTurn(role=MODEL_ROLE, text="Плющ поливають раз на тиждень."),
                ConversationTurn(role=USER_ROLE, text="а взимку?"),
            ],
        )

    async def test_answer_question_after_the_forget_window_starts_a_fresh_conversation(self):
        await self.answer_question("як часто поливати плющ?", conversation_id=ASSISTANT_TOPIC_ID, asked_at=MORNING)

        await self.answer_question(
            "а взимку?", conversation_id=ASSISTANT_TOPIC_ID, asked_at=MORNING + timedelta(minutes=31)
        )

        self.assertEqual(self.language_model.conversations[1], [ConversationTurn(role=USER_ROLE, text="а взимку?")])

    async def test_answer_question_in_another_topic_does_not_see_the_first_conversation(self):
        await self.answer_question("як часто поливати плющ?", conversation_id=ASSISTANT_TOPIC_ID, asked_at=MORNING)

        await self.answer_question("а взимку?", conversation_id=999, asked_at=MORNING + timedelta(minutes=2))

        self.assertEqual(self.language_model.conversations[1], [ConversationTurn(role=USER_ROLE, text="а взимку?")])

    async def test_answer_question_about_a_photo_remembers_the_words_but_not_the_image(self):
        await self.answer_question(
            "що це?",
            conversation_id=ASSISTANT_TOPIC_ID,
            asked_at=MORNING,
            images=[ImageAttachment(data=b"jpeg-bytes")],
        )

        await self.answer_question(
            "а що з листям?", conversation_id=ASSISTANT_TOPIC_ID, asked_at=MORNING + timedelta(minutes=1)
        )

        self.assertEqual(
            self.language_model.conversations[1],
            [
                ConversationTurn(role=USER_ROLE, text="що це?"),
                ConversationTurn(role=MODEL_ROLE, text="Плющ поливають раз на тиждень."),
                ConversationTurn(role=USER_ROLE, text="а що з листям?"),
            ],
        )

    async def test_answer_question_that_the_model_could_not_answer_is_not_remembered(self):
        silent_model = FixedLanguageModel(None, ["Плющ стоїть на кухні."])
        answer_question = AnswerQuestionUseCase(
            silent_model, FixedKnowledgeSource("Плющ стоїть на кухні."), ConversationMemory()
        )
        await answer_question("де плющ?", conversation_id=ASSISTANT_TOPIC_ID, asked_at=MORNING)

        await answer_question("а фікус?", conversation_id=ASSISTANT_TOPIC_ID, asked_at=MORNING + timedelta(minutes=1))

        self.assertEqual(silent_model.conversations[1], [ConversationTurn(role=USER_ROLE, text="а фікус?")])

    async def test_answer_question_with_a_spent_quota_raises_quota_exhausted(self):
        answer_question = AnswerQuestionUseCase(
            ExhaustedLanguageModel(is_daily=True), FixedKnowledgeSource("факти"), ConversationMemory()
        )

        with self.assertRaises(QuotaExhausted) as context:
            await answer_question("де плющ?", conversation_id=ASSISTANT_TOPIC_ID, asked_at=MORNING)

        self.assertEqual(str(context.exception), "The daily free-tier quota is spent")

    async def test_answer_question_with_a_spent_quota_is_not_remembered(self):
        memory = ConversationMemory()
        exhausted = AnswerQuestionUseCase(ExhaustedLanguageModel(), FixedKnowledgeSource("факти"), memory)
        working = AnswerQuestionUseCase(self.language_model, FixedKnowledgeSource("факти"), memory)
        with self.assertRaises(QuotaExhausted):
            await exhausted("де плющ?", conversation_id=ASSISTANT_TOPIC_ID, asked_at=MORNING)

        await working("а фікус?", conversation_id=ASSISTANT_TOPIC_ID, asked_at=MORNING + timedelta(minutes=1))

        self.assertEqual(self.language_model.conversations[0], [ConversationTurn(role=USER_ROLE, text="а фікус?")])

    async def test_answer_question_beyond_the_remembered_turns_keeps_only_the_recent_ones(self):
        language_model = FixedLanguageModel("відповідь")
        answer_question = AnswerQuestionUseCase(
            language_model, FixedKnowledgeSource("факти"), ConversationMemory(remembered_turns=4)
        )
        for number in range(3):
            await answer_question(
                f"питання {number}",
                conversation_id=ASSISTANT_TOPIC_ID,
                asked_at=MORNING + timedelta(minutes=number),
            )

        await answer_question(
            "останнє питання", conversation_id=ASSISTANT_TOPIC_ID, asked_at=MORNING + timedelta(minutes=3)
        )

        self.assertEqual(
            language_model.conversations[3],
            [
                ConversationTurn(role=USER_ROLE, text="питання 1"),
                ConversationTurn(role=MODEL_ROLE, text="відповідь"),
                ConversationTurn(role=USER_ROLE, text="питання 2"),
                ConversationTurn(role=MODEL_ROLE, text="відповідь"),
                ConversationTurn(role=USER_ROLE, text="останнє питання"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
