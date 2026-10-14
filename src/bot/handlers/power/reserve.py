import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.bot.handlers.power.board import PowerBoard
from src.bot.handlers.power.messages import POWER_RESERVE_UNAVAILABLE

logger = logging.getLogger(__name__)

router = Router(name="reserve")


@router.message(Command("reserve"))
async def show_reserve(message: Message, power_board: PowerBoard | None = None) -> None:
    """Bring the standing board down to where the person is already looking, rather than make them scroll up."""
    # the board exists only where the topic and at least one of its halves do, so the command answers
    # instead of going silent
    if power_board is None:
        await message.answer(POWER_RESERVE_UNAVAILABLE)
        return

    await power_board.post()
