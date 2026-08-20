from collections.abc import Callable

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from src.bot.formatting import exceeds_caption_limit
from src.bot.handlers.plants import messages
from src.bot.handlers.plants.formatting import render_plant_card, render_plant_list
from src.bot.handlers.plants.keyboards import (
    PlantAction,
    PlantCallback,
    build_archive_confirmation_keyboard,
    build_archived_plant_keyboard,
    build_plant_card_keyboard,
    build_plant_list_keyboard,
)
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.commands import ArchivePlantCommand, RestorePlantCommand
from src.modules.plant_care.domain import PlantCard
from src.modules.plant_care.use_cases.archive_plant import ArchivePlantUseCase
from src.modules.plant_care.use_cases.list_plants import ListPlantsUseCase
from src.modules.plant_care.use_cases.restore_plant import RestorePlantUseCase
from src.modules.plant_care.use_cases.retrieve_plant_card import RetrievePlantCardUseCase

router = Router(name="plants")


async def send_plant_card(message: Message, card: PlantCard, household_calendar: HouseholdCalendar) -> None:
    text = render_plant_card(card, household_calendar)
    keyboard = build_plant_card_keyboard(card)
    if card.latest_photo is None:
        await message.answer(text, reply_markup=keyboard)
        return
    # a grown card no longer fits a caption, so the photo goes bare and the text keeps the buttons
    if exceeds_caption_limit(text):
        await message.answer_photo(card.latest_photo.telegram_file_id)
        await message.answer(text, reply_markup=keyboard)
        return
    await message.answer_photo(card.latest_photo.telegram_file_id, caption=text, reply_markup=keyboard)


@router.message(Command("list"))
async def list_plants(
    message: Message, uow_factory: Callable[[], UnitOfWork], household_calendar: HouseholdCalendar
) -> None:
    plants = await ListPlantsUseCase(uow=uow_factory(), household_calendar=household_calendar)()
    if not plants:
        await message.answer(messages.NO_PLANTS)
        return

    await message.answer(render_plant_list(plants), reply_markup=build_plant_list_keyboard(plants))


@router.callback_query(PlantCallback.filter(F.action == PlantAction.LIST))
async def list_plants_from_card(
    callback: CallbackQuery, uow_factory: Callable[[], UnitOfWork], household_calendar: HouseholdCalendar
) -> None:
    await callback.answer()
    await list_plants(callback.message, uow_factory, household_calendar)


@router.callback_query(PlantCallback.filter(F.action == PlantAction.OPEN))
async def open_plant_card(
    callback: CallbackQuery,
    callback_data: PlantCallback,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
) -> None:
    await callback.answer()
    card = await RetrievePlantCardUseCase(uow=uow_factory(), household_calendar=household_calendar)(
        callback_data.plant_id
    )
    await send_plant_card(callback.message, card, household_calendar)


@router.callback_query(PlantCallback.filter(F.action == PlantAction.ARCHIVE))
async def confirm_archiving(
    callback: CallbackQuery,
    callback_data: PlantCallback,
    uow_factory: Callable[[], UnitOfWork],
    household_calendar: HouseholdCalendar,
) -> None:
    await callback.answer()
    card = await RetrievePlantCardUseCase(uow=uow_factory(), household_calendar=household_calendar)(
        callback_data.plant_id
    )
    await callback.message.answer(
        messages.ARCHIVE_CONFIRM.format(plant_name=card.name),
        reply_markup=build_archive_confirmation_keyboard(card.id),
    )


@router.callback_query(PlantCallback.filter(F.action == PlantAction.ARCHIVE_CONFIRM))
async def archive_plant(
    callback: CallbackQuery, callback_data: PlantCallback, uow_factory: Callable[[], UnitOfWork]
) -> None:
    plant_name = await ArchivePlantUseCase(uow=uow_factory())(ArchivePlantCommand(plant_id=callback_data.plant_id))
    await callback.answer()
    # the archive is otherwise a one-way door: nothing else in the bot can bring a plant back
    await callback.message.answer(
        messages.PLANT_ARCHIVED.format(plant_name=plant_name),
        reply_markup=build_archived_plant_keyboard(callback_data.plant_id),
    )


@router.callback_query(PlantCallback.filter(F.action == PlantAction.RESTORE))
async def restore_plant(
    callback: CallbackQuery, callback_data: PlantCallback, uow_factory: Callable[[], UnitOfWork]
) -> None:
    plant_name = await RestorePlantUseCase(uow=uow_factory())(RestorePlantCommand(plant_id=callback_data.plant_id))
    await callback.answer()
    await callback.message.edit_text(messages.PLANT_RESTORED.format(plant_name=plant_name))
