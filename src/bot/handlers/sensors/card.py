from collections.abc import Callable

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from src.bot.handlers.sensors.board import ClimateCardBoard
from src.bot.handlers.sensors.contents import gather_climate_card_contents
from src.bot.handlers.sensors.keyboards import ClimateCardCallback
from src.common.config import Settings
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork

router = Router(name="climate_card")


# a pull, never a push: rule 1 — the temperature at home is not news, and a card that spoke every morning
# about nothing would get the topic muted, taking the alerts that matter with it
@router.message(Command("climate"))
async def show_climate(
    message: Message,
    bot: Bot,
    uow_factory: Callable[[], UnitOfWork],
    settings: Settings,
    household_calendar: HouseholdCalendar,
) -> None:
    """The whole flat at a glance — and the one card that says so, moved down here rather than added to."""
    contents = await gather_climate_card_contents(uow_factory, settings, household_calendar)
    board = ClimateCardBoard(
        bot=bot,
        chat_id=message.chat.id,
        topic_id=message.message_thread_id,
        uow_factory=uow_factory,
        household_calendar=household_calendar,
    )

    await board.repost(contents)


@router.callback_query(ClimateCardCallback.filter())
async def refresh_climate_card(
    callback: CallbackQuery,
    bot: Bot,
    uow_factory: Callable[[], UnitOfWork],
    settings: Settings,
    household_calendar: HouseholdCalendar,
) -> None:
    """The numbers on the card that was pressed, brought up to date in place."""
    await callback.answer()
    contents = await gather_climate_card_contents(uow_factory, settings, household_calendar)
    board = ClimateCardBoard(
        bot=bot,
        chat_id=callback.message.chat.id,
        topic_id=callback.message.message_thread_id,
        uow_factory=uow_factory,
        household_calendar=household_calendar,
    )

    await board.refresh_message(callback.message.message_id, contents)
