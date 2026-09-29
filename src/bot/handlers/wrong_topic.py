from collections.abc import Callable

from aiogram import Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from src.bot import messages
from src.bot.handlers.start import retrieve_topic_module_name
from src.infrastructure.db.uow import UnitOfWork

# must stay included after every module router — it answers whatever they declined
router = Router(name="wrong_topic")

MODULE_COMMANDS = tuple(command for commands in messages.MODULE_COMMANDS.values() for command in commands)


@router.message(Command(*MODULE_COMMANDS))
async def point_to_the_right_place(
    message: Message, command: CommandObject, uow_factory: Callable[[], UnitOfWork]
) -> None:
    """Reached only when every module router declined the command, which means it was typed where none answers it."""
    if message.chat.type == ChatType.PRIVATE:
        await message.answer(messages.ONLY_IN_THE_GROUP)
        return

    module_name = await retrieve_topic_module_name(message, uow_factory)
    is_a_known_topic = module_name in messages.MODULE_HELP
    if is_a_known_topic and command.command not in messages.MODULE_COMMANDS.get(module_name, ()):
        await message.answer(
            messages.NO_SUCH_COMMAND_HERE.format(
                command=command.command,
                topic_help=messages.TOPIC_HELP[module_name],
                places=", ".join(
                    messages.MODULE_TITLES[owner]
                    for owner, commands in messages.MODULE_COMMANDS.items()
                    if command.command in commands
                ),
            )
        )
        return

    await message.answer(messages.WRONG_TOPIC)


@router.callback_query()
async def answer_a_stale_button(callback: CallbackQuery) -> None:
    """A button older than 48 hours arrives without its topic, so no module can claim it — say so instead of hanging."""
    await callback.answer(messages.STALE_BUTTON, show_alert=True)
