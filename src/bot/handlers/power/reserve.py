import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.bot.handlers.power.messages import POWER_RESERVE_UNAVAILABLE
from src.bot.handlers.power.reserve_board import ReserveBoard

logger = logging.getLogger(__name__)

router = Router(name="reserve")


@router.message(Command("reserve"))
async def show_reserve(message: Message, reserve_board: ReserveBoard | None = None) -> None:
    """Bring the standing board down to where the person is already looking, rather than make them scroll up."""
    # the board exists only where all three layers can be read, so the command answers instead of going silent
    if reserve_board is None:
        await message.answer(POWER_RESERVE_UNAVAILABLE)
        return

    await reserve_board.post()
