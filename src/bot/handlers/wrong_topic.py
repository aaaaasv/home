from aiogram import Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from src.bot import messages

# must stay included after every module router — it answers whatever they declined
router = Router(name="wrong_topic")

MODULE_COMMANDS = ("today", "add", "history", "list", "later", "track", "ac", "eco", "conserve", "pi", "bus")


@router.message(Command(*MODULE_COMMANDS))
async def point_to_the_right_place(message: Message) -> None:
    """Reached only when every module router declined the command, which means it was typed where no module listens."""
    if message.chat.type == ChatType.PRIVATE:
        await message.answer(messages.ONLY_IN_THE_GROUP)
        return

    await message.answer(messages.WRONG_TOPIC)


@router.callback_query()
async def answer_a_stale_button(callback: CallbackQuery) -> None:
    """A button older than 48 hours arrives without its topic, so no module can claim it — say so instead of hanging."""
    await callback.answer(messages.STALE_BUTTON, show_alert=True)
