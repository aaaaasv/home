import unittest
from types import SimpleNamespace

from anthropic import APIConnectionError
from httpx import Request

from src.infrastructure.adapters.claude_client import ClaudeClient, text_of
from src.modules.model_budget.services.usage_ledger import BudgetSpent


class RecordingLedger:
    """Counts what the client asked of the budget, and can be told the allowance is gone."""

    def __init__(self, is_spent: bool = False):
        self.is_spent = is_spent
        self.checks = 0
        self.recorded: list[dict] = []

    async def refuse_if_spent(self) -> None:
        self.checks += 1
        if self.is_spent:
            raise BudgetSpent(is_daily=True)

    async def record(self, purpose: str, model: str, input_tokens: int, output_tokens: int) -> None:
        self.recorded.append(
            {"purpose": purpose, "model": model, "input_tokens": input_tokens, "output_tokens": output_tokens}
        )


def build_response(text: str = "так", stop_reason: str = "end_turn", input_tokens: int = 1300, output: int = 80):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output),
    )


class StubMessages:
    def __init__(self, response=None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.requests: list[dict] = []

    async def create(self, **request):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.response


class ClaudeClientTestCase(unittest.IsolatedAsyncioTestCase):
    """Every paid call passes the budget on the way in and is billed on the way out."""

    def build_client(self, ledger: RecordingLedger, response=None, error: Exception | None = None):
        client = ClaudeClient(api_key="test-key", ledger=ledger)
        client.client = SimpleNamespace(messages=StubMessages(response=response, error=error))
        return client

    async def ask(self, client) -> object:
        return await client.complete(purpose="Photo review", model="claude-opus-5-5", max_tokens=100, messages=[])

    async def test_complete_bills_the_ledger_with_the_tokens_the_answer_used(self):
        ledger = RecordingLedger()

        await self.ask(self.build_client(ledger, response=build_response()))

        self.assertEqual(
            ledger.recorded,
            [{"purpose": "Photo review", "model": "claude-opus-5-5", "input_tokens": 1300, "output_tokens": 80}],
        )

    async def test_complete_asks_the_ledger_before_it_spends_anything(self):
        ledger = RecordingLedger(is_spent=True)
        client = self.build_client(ledger, response=build_response())

        with self.assertRaises(BudgetSpent):
            await self.ask(client)

        # the refusal has to come before the request, or it has already cost what it was meant to save
        self.assertEqual(client.client.messages.requests, [])

    async def test_complete_with_a_refused_call_bills_nothing(self):
        ledger = RecordingLedger()
        error = APIConnectionError(request=Request("POST", "https://api.anthropic.com/v1/messages"))

        answer = await self.ask(self.build_client(ledger, error=error))

        self.assertIsNone(answer)
        self.assertEqual(ledger.recorded, [])

    async def test_complete_with_an_answer_cut_short_bills_it_and_returns_nothing(self):
        """Truncated json is not safe to parse, but the tokens were spent and must be counted."""
        ledger = RecordingLedger()

        answer = await self.ask(self.build_client(ledger, response=build_response(stop_reason="max_tokens")))

        self.assertIsNone(answer)
        self.assertEqual(len(ledger.recorded), 1)


class TextOfTestCase(unittest.TestCase):
    def test_text_of_joins_every_text_block_and_leaves_the_rest_out(self):
        response = SimpleNamespace(
            content=[
                SimpleNamespace(type="thinking", thinking="…"),
                SimpleNamespace(type="text", text="перша. "),
                SimpleNamespace(type="text", text="друга."),
            ]
        )

        self.assertEqual(text_of(response), "перша. друга.")

    def test_text_of_an_answer_made_only_of_tool_calls_is_none(self):
        response = SimpleNamespace(content=[SimpleNamespace(type="server_tool_use", id="x")])

        self.assertIsNone(text_of(response))


class StubToolMessages:
    """Answers with a scripted sequence of responses, recording each conversation it was sent."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.conversations: list[list] = []

    async def create(self, **request):
        self.conversations.append(request["messages"])
        return self.responses.pop(0)


def build_tool_call(name: str, arguments: dict, tool_use_id: str = "call-1"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", id=tool_use_id, name=name, input=arguments)],
        stop_reason="tool_use",
        usage=SimpleNamespace(input_tokens=500, output_tokens=40),
    )


class CompleteWithToolsTestCase(unittest.IsolatedAsyncioTestCase):
    """The model may ask for more on its way to answering, and every round is billed on its own."""

    def build_client(self, ledger, responses):
        client = ClaudeClient(api_key="test-key", ledger=ledger)
        client.client = SimpleNamespace(messages=StubToolMessages(responses))
        return client

    async def ask(self, client, run_tool):
        return await client.complete_with_tools(
            purpose="Photo review",
            model="claude-opus-5-5",
            tools=[{"name": "care_log"}],
            run_tool=run_tool,
            messages=[{"role": "user", "content": "дивись"}],
        )

    async def test_an_answer_that_needs_no_tool_comes_straight_back(self):
        ledger = RecordingLedger()
        asked = []

        answer = await self.ask(self.build_client(ledger, [build_response()]), lambda *_: asked.append(_))

        self.assertEqual(text_of(answer), "так")
        self.assertEqual(asked, [])
        self.assertEqual(len(ledger.recorded), 1)

    async def test_a_tool_the_model_asks_for_is_run_and_its_answer_sent_back(self):
        ledger = RecordingLedger()
        client = self.build_client(ledger, [build_tool_call("care_log", {}), build_response(text="полито вчора")])

        async def run_tool(name, arguments):
            return f"журнал {name}"

        answer = await self.ask(client, run_tool)

        self.assertEqual(text_of(answer), "полито вчора")
        last_turn = client.client.messages.conversations[-1][-1]
        self.assertEqual(
            last_turn["content"], [{"type": "tool_result", "tool_use_id": "call-1", "content": "журнал care_log"}]
        )

    async def test_every_round_is_billed_separately(self):
        ledger = RecordingLedger()
        client = self.build_client(ledger, [build_tool_call("care_log", {}), build_response()])

        await self.ask(client, lambda name, arguments: _answer("щось"))

        self.assertEqual(len(ledger.recorded), 2)

    async def test_a_tool_that_raises_is_reported_to_the_model_rather_than_losing_the_review(self):
        ledger = RecordingLedger()
        client = self.build_client(ledger, [build_tool_call("care_log", {}), build_response()])

        async def run_tool(name, arguments):
            raise RuntimeError("база впала")

        await self.ask(client, run_tool)

        last_turn = client.client.messages.conversations[-1][-1]
        self.assertEqual(last_turn["content"][0]["content"], "Інструмент не відповів.")

    async def test_a_model_that_never_stops_asking_is_cut_off(self):
        ledger = RecordingLedger()
        client = self.build_client(ledger, [build_tool_call("care_log", {}) for _ in range(6)])

        answer = await client.complete_with_tools(
            purpose="Photo review",
            model="claude-opus-5-5",
            tools=[{"name": "care_log"}],
            run_tool=lambda name, arguments: _answer("ще"),
            messages=[{"role": "user", "content": "дивись"}],
            max_rounds=6,
        )

        self.assertIsNone(answer)


async def _answer(text: str) -> str:
    return text
