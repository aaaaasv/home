from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from src.bot.handlers.transit.board import TransitBoard
from src.bot.handlers.transit.keyboards import TransitCallback
from src.bot.handlers.transit.messages import TRANSIT_REFRESHING

router = Router(name="transit_arrivals")


@router.message(Command("bus", "транспорт"))
async def show_transit(message: Message, transit_board: TransitBoard) -> None:
    await transit_board.post()


@router.callback_query(TransitCallback.filter())
async def refresh_transit(callback: CallbackQuery, transit_board: TransitBoard | None = None) -> None:
    # a status banner up front while the feed is polled; the refreshed card itself is the result
    await callback.answer(TRANSIT_REFRESHING)
    # the button rides on a board that only exists when transit is enabled, but a stale one may outlive a disable
    if transit_board is not None:
        await transit_board.resume()
