"""The plant, care and schedule buttons."""
from enum import StrEnum
from typing import NamedTuple

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.formatting import pluralize_days, shorten_for_button
from src.bot.handlers.plants.formatting import (
    format_ideal_humidity,
    format_ideal_temperature,
    render_care_card_caption,
    task_action,
    task_emoji,
    task_label,
)
from src.bot.handlers.plants.messages import (
    CARE_POSTPONE_BUTTON,
    CARE_SKIP_BUTTON,
    CARE_TASK_LABELS,
    CARE_UNDO_BUTTON,
    OVERDUE_EMOJI,
    PLANT_EMOJI,
    PLANT_FIELD_LABELS,
    PLANT_RESTORE_BUTTON,
    SCHEDULE_REMOVE_BUTTON,
)
from src.bot.services.posted_message_tracker import build_care_task_reference
from src.common.constants import CareTaskType, PlantField
from src.modules.plant_care.domain import CareDigest, DueCareTask, PlantCard, PlantSummary

INTERVAL_PRESET_DAYS = (1, 3, 7, 14, 30)
CUSTOM_INTERVAL_MARKER = 0


class PlantAction(StrEnum):
    OPEN = "open"
    PHOTOS = "photos"
    ADD_PHOTO = "add_photo"
    # same upload flow as ADD_PHOTO, but entered from a digest card the bot must delete afterwards
    ADD_PHOTO_DUE = "photo_due"
    EDIT = "edit"
    ARCHIVE = "archive"
    ARCHIVE_CONFIRM = "archive_confirm"
    RESTORE = "restore"
    LIST = "list"


class ScheduleAction(StrEnum):
    CHOOSE_TASK = "choose_task"
    CHOOSE_INTERVAL = "choose_interval"
    SET = "set"
    REMOVE = "remove"
    EDIT_INSTRUCTIONS = "instructions"
    POSTPONE = "postpone"
    UNDO = "undo"
    CONFIRM_REMOVE = "confirm_remove"


class CareCallback(CallbackData, prefix="care"):
    plant_id: int
    task_type: CareTaskType
    force: bool = False


class PlantCallback(CallbackData, prefix="plant"):
    action: PlantAction
    plant_id: int = 0


class ScheduleCallback(CallbackData, prefix="schedule"):
    action: ScheduleAction
    plant_id: int
    task_type: CareTaskType | None = None
    interval_days: int = CUSTOM_INTERVAL_MARKER


class EditPlantCallback(CallbackData, prefix="edit_plant"):
    plant_id: int
    field: PlantField


class NewPlantIntervalCallback(CallbackData, prefix="new_interval"):
    interval_days: int


class CareCard(NamedTuple):
    photo_file_id: str | None
    caption: str
    keyboard: InlineKeyboardMarkup
    task_reference: str


def build_care_cards(digest: CareDigest) -> list[CareCard]:
    # one card per due task: the plant's photo, a caption with the how-to, and two ways out — do it, or defer it
    return [
        CareCard(
            photo_file_id=task.photo_file_id,
            caption=render_care_card_caption(task),
            keyboard=build_care_card_keyboard(task),
            task_reference=build_care_task_reference(task.plant_id, task.task_type),
        )
        for task in digest.tasks
    ]


def build_care_card_keyboard(task: DueCareTask) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"{task_emoji(task.task_type)} {task_action(task.task_type)}",
        callback_data=_build_care_card_callback(task),
    )
    # both defer via POSTPONE; the use case turns a skippable task's defer into a full cycle, so the label just
    # promises "skip" instead of naming a day count
    defer_text = (
        CARE_SKIP_BUTTON if task.is_skippable else CARE_POSTPONE_BUTTON.format(days=pluralize_days(task.postpone_days))
    )
    builder.button(
        text=defer_text,
        callback_data=ScheduleCallback(
            action=ScheduleAction.POSTPONE, plant_id=task.plant_id, task_type=task.task_type
        ),
    )
    # one per row: side by side, "нагадати через 14 днів" gets squeezed against the short record button
    builder.adjust(1)
    return builder.as_markup()


def build_archived_plant_keyboard(plant_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=PLANT_RESTORE_BUTTON, callback_data=PlantCallback(action=PlantAction.RESTORE, plant_id=plant_id)
    )
    return builder.as_markup()


def build_schedule_remove_keyboard(plant_id: int, task_type: CareTaskType) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=SCHEDULE_REMOVE_BUTTON,
        callback_data=ScheduleCallback(action=ScheduleAction.REMOVE, plant_id=plant_id, task_type=task_type),
    )
    builder.button(text="Ні", callback_data=PlantCallback(action=PlantAction.OPEN, plant_id=plant_id))
    return builder.as_markup()


def build_recorded_care_keyboard(plant_id: int, task_type: CareTaskType) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=CARE_UNDO_BUTTON,
        callback_data=ScheduleCallback(action=ScheduleAction.UNDO, plant_id=plant_id, task_type=task_type),
    )
    return builder.as_markup()


def _build_care_card_callback(task: DueCareTask) -> CallbackData:
    # a photo is not recorded by tapping — the button opens the upload flow, and the photo itself closes the task
    if task.task_type == CareTaskType.PHOTO:
        return PlantCallback(action=PlantAction.ADD_PHOTO_DUE, plant_id=task.plant_id)
    return CareCallback(plant_id=task.plant_id, task_type=task.task_type)


def build_force_care_keyboard(plant_id: int, task_type: CareTaskType) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Так, записати",
        callback_data=CareCallback(plant_id=plant_id, task_type=task_type, force=True),
    )
    builder.button(text="Ні", callback_data=PlantCallback(action=PlantAction.OPEN, plant_id=plant_id))
    return builder.as_markup()


def build_plant_list_keyboard(plants: list[PlantSummary]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plant in plants:
        builder.button(
            text=f"{_plant_status_emoji(plant)} {plant.name}",
            callback_data=PlantCallback(action=PlantAction.OPEN, plant_id=plant.id),
        )
    builder.adjust(2)
    return builder.as_markup()


def build_plant_card_keyboard(card: PlantCard) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for schedule in card.schedules:
        # photo is scheduled like care but recorded by the upload button below, so it gets no record button here
        if schedule.task_type == CareTaskType.PHOTO:
            continue
        builder.button(
            text=f"{task_emoji(schedule.task_type)} {task_action(schedule.task_type)}",
            callback_data=CareCallback(plant_id=card.id, task_type=schedule.task_type),
        )
    builder.adjust(2)

    photo_row = [
        InlineKeyboardButton(
            text="📸 Додати фото",
            callback_data=PlantCallback(action=PlantAction.ADD_PHOTO, plant_id=card.id).pack(),
        )
    ]
    if card.photo_count:
        photo_row.append(
            InlineKeyboardButton(
                text=f"🖼 Фото ({card.photo_count})",
                callback_data=PlantCallback(action=PlantAction.PHOTOS, plant_id=card.id).pack(),
            )
        )
    builder.row(*photo_row)

    builder.row(
        InlineKeyboardButton(
            text="➕ Догляд",
            callback_data=ScheduleCallback(action=ScheduleAction.CHOOSE_TASK, plant_id=card.id).pack(),
        ),
        InlineKeyboardButton(
            text="✏️ Змінити",
            callback_data=PlantCallback(action=PlantAction.EDIT, plant_id=card.id).pack(),
        ),
        InlineKeyboardButton(
            text="🗑 Прибрати",
            callback_data=PlantCallback(action=PlantAction.ARCHIVE, plant_id=card.id).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="⬅️ До списку",
            callback_data=PlantCallback(action=PlantAction.LIST).pack(),
        )
    )
    return builder.as_markup()


def build_plant_edit_keyboard(card: PlantCard) -> InlineKeyboardMarkup:
    current_values: dict[PlantField, str | None] = {
        PlantField.NAME: card.name,
        PlantField.SPECIES: card.species,
        PlantField.LOCATION: card.location,
        PlantField.NOTES: card.notes,
        PlantField.TEMPERATURE_RANGE: format_ideal_temperature(card),
        PlantField.HUMIDITY_RANGE: format_ideal_humidity(card),
    }
    builder = InlineKeyboardBuilder()
    for field, label in PLANT_FIELD_LABELS.items():
        builder.row(
            InlineKeyboardButton(
                text=f"✏️ {label}: {shorten_for_button(current_values[field])}",
                callback_data=EditPlantCallback(plant_id=card.id, field=field).pack(),
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=PlantCallback(action=PlantAction.OPEN, plant_id=card.id).pack(),
        )
    )
    return builder.as_markup()


def build_task_type_keyboard(card: PlantCard) -> InlineKeyboardMarkup:
    schedules_by_task_type = {schedule.task_type: schedule for schedule in card.schedules}
    builder = InlineKeyboardBuilder()

    for task_type in CARE_TASK_LABELS:
        schedule = schedules_by_task_type.get(task_type)
        if schedule is None:
            builder.row(
                InlineKeyboardButton(
                    text=f"➕ {task_emoji(task_type)} {task_label(task_type)}",
                    callback_data=_choose_interval_callback(card.id, task_type),
                )
            )
            continue

        current_interval = pluralize_days(schedule.interval_days)
        builder.row(
            InlineKeyboardButton(
                text=f"✏️ {task_emoji(task_type)} {task_label(task_type)} — раз на {current_interval}",
                callback_data=_choose_interval_callback(card.id, task_type),
            )
        )

        instructions_label = "📝 інструкція ✓" if schedule.instructions else "📝 інструкція"
        second_row = [
            InlineKeyboardButton(
                text=instructions_label,
                callback_data=ScheduleCallback(
                    action=ScheduleAction.EDIT_INSTRUCTIONS, plant_id=card.id, task_type=task_type
                ).pack(),
            )
        ]
        if task_type != CareTaskType.WATERING:
            second_row.append(
                InlineKeyboardButton(
                    text="➖",
                    callback_data=ScheduleCallback(
                        action=ScheduleAction.CONFIRM_REMOVE, plant_id=card.id, task_type=task_type
                    ).pack(),
                )
            )
        builder.row(*second_row)

    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=PlantCallback(action=PlantAction.OPEN, plant_id=card.id).pack(),
        )
    )
    return builder.as_markup()


def _choose_interval_callback(plant_id: int, task_type: CareTaskType) -> str:
    return ScheduleCallback(action=ScheduleAction.CHOOSE_INTERVAL, plant_id=plant_id, task_type=task_type).pack()


def build_schedule_interval_keyboard(plant_id: int, task_type: CareTaskType) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for interval_days in INTERVAL_PRESET_DAYS:
        builder.button(
            text=f"раз на {pluralize_days(interval_days)}",
            callback_data=ScheduleCallback(
                action=ScheduleAction.SET,
                plant_id=plant_id,
                task_type=task_type,
                interval_days=interval_days,
            ),
        )
    builder.button(
        text="✏️ свій інтервал",
        callback_data=ScheduleCallback(
            action=ScheduleAction.SET,
            plant_id=plant_id,
            task_type=task_type,
            interval_days=CUSTOM_INTERVAL_MARKER,
        ),
    )
    builder.adjust(2)
    return builder.as_markup()


def build_new_plant_interval_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for interval_days in INTERVAL_PRESET_DAYS:
        builder.button(
            text=f"раз на {pluralize_days(interval_days)}",
            callback_data=NewPlantIntervalCallback(interval_days=interval_days),
        )
    builder.button(
        text="✏️ свій інтервал", callback_data=NewPlantIntervalCallback(interval_days=CUSTOM_INTERVAL_MARKER)
    )
    builder.adjust(2)
    return builder.as_markup()


def build_archive_confirmation_keyboard(plant_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🗑 Так, прибрати",
        callback_data=PlantCallback(action=PlantAction.ARCHIVE_CONFIRM, plant_id=plant_id),
    )
    builder.button(text="Ні", callback_data=PlantCallback(action=PlantAction.OPEN, plant_id=plant_id))
    return builder.as_markup()


def _plant_status_emoji(plant: PlantSummary) -> str:
    most_urgent_schedule = plant.most_urgent_schedule
    if most_urgent_schedule is None:
        return PLANT_EMOJI
    if most_urgent_schedule.overdue_days > 0:
        return OVERDUE_EMOJI
    if most_urgent_schedule.is_due:
        return task_emoji(most_urgent_schedule.task_type)
    return PLANT_EMOJI
