from collections.abc import Callable

from aiogram import Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from src.bot import messages
from src.bot.message_cleanup import delete_quietly, sweep_transient_messages
from src.infrastructure.db.uow import UnitOfWork

router = Router(name="start")


@router.message(CommandStart())
async def show_welcome(message: Message) -> None:
    if message.chat.type == ChatType.PRIVATE:
        await message.answer(messages.PRIVATE_WELCOME)
        return
    await message.answer(messages.WELCOME)


@router.message(Command("help"))
async def show_help(message: Message, uow_factory: Callable[[], UnitOfWork]) -> None:
    await message.answer(await _render_help(message, uow_factory))


async def _render_help(message: Message, uow_factory: Callable[[], UnitOfWork]) -> str:
    # inside a module topic, /help lists only that topic's commands; elsewhere it falls back to the full welcome
    if message.chat.type == ChatType.PRIVATE:
        return messages.PRIVATE_WELCOME
    if message.message_thread_id is not None:
        async with uow_factory() as uow:
            topic = await uow.forum_topics.retrieve_by_thread_id(message.chat.id, message.message_thread_id)
        if topic is not None and topic.module_name in messages.TOPIC_HELP:
            return messages.TOPIC_HELP[topic.module_name]
    return messages.WELCOME


@router.message(Command("chatid"))
async def show_chat_id(message: Message) -> None:
    lines = [
        f"chat_id: <code>{message.chat.id}</code>",
        f"user_id: <code>{message.from_user.id}</code>",
    ]
    if message.is_topic_message:
        lines.append(f"topic_id: <code>{message.message_thread_id}</code>")

    await message.answer("\n".join(lines))


@router.message(Command("cancel"))
async def cancel_current_action(message: Message, state: FSMContext) -> None:
    # sweep the abandoned flow's prompts and menus, then drop the /cancel command itself — the point of cancelling
    # is a clean chat, so a "Скасовано." message of its own would be exactly the clutter we are removing
    collected_data = await state.get_data()
    await state.clear()
    await sweep_transient_messages(message.bot, message.chat.id, collected_data)
    await delete_quietly(message)
