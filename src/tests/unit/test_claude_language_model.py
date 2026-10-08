import unittest
from types import SimpleNamespace

from src.infrastructure.adapters.claude_language_model import WEB_SEARCH_TOOL, ClaudeLanguageModel, build_turn
from src.modules.assistant.services.language_model import (
    MODEL_ROLE,
    USER_ROLE,
    ConversationTurn,
    ImageAttachment,
    QuotaExhausted,
)
from src.modules.model_budget.services.usage_ledger import BudgetSpent


class StubClaudeClient:
    def __init__(self, text: str | None = "так", refusal: Exception | None = None):
        self.text = text
        self.refusal = refusal
        self.requests: list[dict] = []

    async def complete(self, purpose: str, model: str, **request):
        self.requests.append({"purpose": purpose, "model": model, **request})
        if self.refusal is not None:
            raise self.refusal
        if self.text is None:
            return None
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.text)])


class ClaudeLanguageModelTestCase(unittest.IsolatedAsyncioTestCase):
    def build_model(self, client) -> ClaudeLanguageModel:
        return ClaudeLanguageModel(client=client, model="claude-sonnet-5-5", effort="low")

    async def test_generate_returns_the_answer_text(self):
        answer = await self.build_model(StubClaudeClient(text="Схоже на перелив.")).generate(
            [ConversationTurn(role=USER_ROLE, text="чому жовтіє?")], "Факти про дім:"
        )

        self.assertEqual(answer, "Схоже на перелив.")

    async def test_generate_offers_the_model_a_web_search(self):
        client = StubClaudeClient()

        await self.build_model(client).generate([ConversationTurn(role=USER_ROLE, text="питання")], "факти")

        self.assertEqual(client.requests[0]["tools"], [WEB_SEARCH_TOOL])
        self.assertEqual(client.requests[0]["system"], "факти")

    async def test_generate_asks_for_the_effort_it_was_configured_with(self):
        """Somebody is watching the chat for this answer, so the wait is the cost."""
        client = StubClaudeClient()

        await self.build_model(client).generate([ConversationTurn(role=USER_ROLE, text="питання")], "факти")

        self.assertEqual(client.requests[0]["output_config"], {"effort": "low"})

    async def test_generate_with_the_budget_spent_tells_the_family_in_the_words_it_already_has(self):
        """The topic has a message for a spent quota; an allowance is the same thing to whoever is waiting."""
        client = StubClaudeClient(refusal=BudgetSpent(is_daily=True))

        with self.assertRaises(QuotaExhausted) as context:
            await self.build_model(client).generate([ConversationTurn(role=USER_ROLE, text="питання")], "факти")

        self.assertTrue(context.exception.is_daily)

    async def test_generate_with_a_model_that_did_not_answer_returns_nothing(self):
        answer = await self.build_model(StubClaudeClient(text=None)).generate(
            [ConversationTurn(role=USER_ROLE, text="питання")], "факти"
        )

        self.assertIsNone(answer)


class BuildTurnTestCase(unittest.TestCase):
    """The conversation is remembered in gemini's words, so the model's own turn has to be renamed."""

    def test_build_turn_renames_the_models_own_turn_to_anthropics_word_for_it(self):
        self.assertEqual(build_turn(ConversationTurn(role=MODEL_ROLE, text="так"))["role"], "assistant")

    def test_build_turn_leaves_the_familys_turn_alone(self):
        self.assertEqual(build_turn(ConversationTurn(role=USER_ROLE, text="питання"))["role"], "user")

    def test_build_turn_inlines_an_image_after_the_text(self):
        turn = ConversationTurn(role=USER_ROLE, text="що це?", images=(ImageAttachment(data=b"\x00\x01"),))

        self.assertEqual(
            build_turn(turn)["content"],
            [
                {"type": "text", "text": "що це?"},
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "AAE="}},
            ],
        )
