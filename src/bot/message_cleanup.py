import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReactionTypeEmoji

logger = logging.getLogger(__name__)

# a flow posts prompts and menus that exist only to drive it; their ids collect here so the flow can drop them
# when it ends — on success or on /cancel — leaving only the board (or card) as the record of what happened
TRANSIENT_MESSAGE_IDS_KEY = "transient_message_ids"

# telegram only accepts reactions from its default set, and 👍 is always in it
CAPTURED_REACTION = "👍"


async def delete_quietly(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        # already gone, or past telegram's delete window — what the flow produced is what matters, not this
        pass


async def delete_message_quietly(bot: Bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramBadRequest:
        pass


async def remember_transient_message(state: FSMContext, message: Message) -> None:
    data = await state.get_data()
    message_ids = list(data.get(TRANSIENT_MESSAGE_IDS_KEY, ()))
    message_ids.append(message.message_id)
    await state.update_data(**{TRANSIENT_MESSAGE_IDS_KEY: message_ids})


async def sweep_transient_messages(bot: Bot, chat_id: int, collected_data: dict) -> None:
    # take the ids from a snapshot the caller already read, so it works after state.clear() has wiped the store
    for message_id in collected_data.get(TRANSIENT_MESSAGE_IDS_KEY, ()):
        await delete_message_quietly(bot, chat_id, message_id)


async def replace_prompt(state: FSMContext, prompt: Message) -> None:
    # a step-by-step flow shows one question at a time: drop whatever prompt preceded this one and track this one,
    # so the wizard never grows into a heap and /cancel still has exactly the visible prompt to sweep
    data = await state.get_data()
    for message_id in data.get(TRANSIENT_MESSAGE_IDS_KEY, ()):
        await delete_message_quietly(prompt.bot, prompt.chat.id, message_id)
    await state.update_data(**{TRANSIENT_MESSAGE_IDS_KEY: [prompt.message_id]})


async def confirm_captured(message: Message) -> None:
    # the item now lives in the self-editing board, so the raw message is clutter — delete it (react if we cannot)
    try:
        await message.delete()
        return
    except TelegramBadRequest:
        pass
    try:
        await message.react([ReactionTypeEmoji(emoji=CAPTURED_REACTION)])
    except TelegramBadRequest:
        logger.info("Could not delete or react to a captured message")
