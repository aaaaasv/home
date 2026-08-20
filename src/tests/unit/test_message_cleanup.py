import unittest
from types import SimpleNamespace

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from src.bot.handlers.start import cancel_current_action
from src.bot.message_cleanup import TRANSIENT_MESSAGE_IDS_KEY, remember_transient_message, sweep_transient_messages
from src.tests.fakes import RecordingBot

CHAT_ID = 10


class DummyStates(StatesGroup):
    waiting = State()


class FakeMessage:
    """The minimum a handler touches on a message: its bot, chat, id, and self-deletion"""

    def __init__(self, bot: RecordingBot, message_id: int):
        self.bot = bot
        self.chat = SimpleNamespace(id=CHAT_ID)
        self.message_id = message_id

    async def delete(self) -> None:
        await self.bot.delete_message(self.chat.id, self.message_id)


class MessageCleanupTestCase(unittest.IsolatedAsyncioTestCase):
    def build_state(self) -> FSMContext:
        return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=CHAT_ID, user_id=20))

    async def test_remember_transient_message_collects_ids_in_order(self):
        state = self.build_state()
        bot = RecordingBot()

        await remember_transient_message(state, FakeMessage(bot, 101))
        await remember_transient_message(state, FakeMessage(bot, 102))

        data = await state.get_data()
        self.assertEqual(data[TRANSIENT_MESSAGE_IDS_KEY], [101, 102])

    async def test_remember_transient_message_keeps_other_flow_data(self):
        state = self.build_state()
        bot = RecordingBot()
        await state.update_data(item_id=7)

        await remember_transient_message(state, FakeMessage(bot, 101))

        data = await state.get_data()
        self.assertEqual(data, {"item_id": 7, TRANSIENT_MESSAGE_IDS_KEY: [101]})

    async def test_sweep_transient_messages_deletes_every_remembered_id(self):
        bot = RecordingBot()

        await sweep_transient_messages(bot, CHAT_ID, {TRANSIENT_MESSAGE_IDS_KEY: [201, 202]})

        self.assertEqual(bot.deleted, [201, 202])

    async def test_sweep_transient_messages_without_any_ids_deletes_nothing(self):
        bot = RecordingBot()

        await sweep_transient_messages(bot, CHAT_ID, {"item_id": 7})

        self.assertEqual(bot.deleted, [])

    async def test_cancel_sweeps_the_prompts_then_drops_the_cancel_command(self):
        state = self.build_state()
        bot = RecordingBot()
        await state.set_state(DummyStates.waiting)
        await remember_transient_message(state, FakeMessage(bot, 301))
        command_message = FakeMessage(bot, 302)

        await cancel_current_action(command_message, state)

        self.assertEqual(bot.deleted, [301, 302])
        self.assertEqual(bot.sent, [])
        self.assertIsNone(await state.get_state())

    async def test_cancel_with_no_active_flow_drops_the_command_and_stays_silent(self):
        state = self.build_state()
        bot = RecordingBot()
        command_message = FakeMessage(bot, 400)

        await cancel_current_action(command_message, state)

        self.assertEqual(bot.deleted, [400])
        self.assertEqual(bot.sent, [])
