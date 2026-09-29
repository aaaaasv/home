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


# the two are the same question — «що тут можна» — and /start used to answer it with all nine modules in any topic
@router.message(CommandStart())
@router.message(Command("help"))
async def show_help(message: Message, uow_factory: Callable[[], UnitOfWork]) -> None:
    """Inside a module topic, that topic's commands; in General the full welcome; in a private chat, a pointer."""
    if message.chat.type == ChatType.PRIVATE:
        await message.answer(messages.PRIVATE_WELCOME)
        return

    module_name = await retrieve_topic_module_name(message, uow_factory)
    await message.answer(messages.TOPIC_HELP.get(module_name, messages.WELCOME))


async def retrieve_topic_module_name(message: Message, uow_factory: Callable[[], UnitOfWork]) -> str | None:
    """Which module owns the topic this message was sent in — None in General, where no module does."""
    if message.message_thread_id is None:
        return None
    async with uow_factory() as uow:
        topic = await uow.forum_topics.retrieve_by_thread_id(message.chat.id, message.message_thread_id)
    return topic.module_name if topic is not None else None


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
