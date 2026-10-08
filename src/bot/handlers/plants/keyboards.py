"""The plant, care and schedule buttons."""
from enum import StrEnum
from typing import NamedTuple

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.formatting import pluralize_days, shorten_for_button
from src.bot.handlers.plants.care_card_reference import TASK_TYPE_ORDER, build_care_card_reference
from src.bot.handlers.plants.formatting import (
    format_ideal_humidity,
    format_ideal_temperature,
    render_care_card_caption,
    task_action,
    task_label,
)
from src.bot.handlers.plants.messages import (
    CARE_POSTPONE_BUTTON,
    CARE_TASK_LABELS,
    CARE_UNDO_BUTTON,
    PHOTO_HISTORY_NEWER_BUTTON,
    PHOTO_HISTORY_OLDER_BUTTON,
    PHOTO_REVIEW_NOW_BUTTON,
    PHOTO_REVIEW_RETRY_BUTTON,
    PLANT_FIELD_LABELS,
    PLANT_RESTORE_BUTTON,
    SCHEDULE_REMOVE_BUTTON,
)
from src.common.constants import CareTaskType, PlantField
from src.modules.plant_care.domain import CareDigest, DueCareTask, PlantCard, PlantSummary
from src.modules.plant_care.services.plant_air import PlantAir

# telegram colours a button instead of decorating it: green for the action the card exists for, red for the
# one that cannot be taken back
SUCCESS_STYLE = "success"
DANGER_STYLE = "danger"

INTERVAL_PRESET_DAYS = (1, 3, 7, 14, 30)
CUSTOM_INTERVAL_MARKER = 0


class PlantAction(StrEnum):
    OPEN = "open"
    PHOTOS = "photos"
    ADD_PHOTO = "add_photo"
    REVIEW_PHOTO = "review_photo"
    REVIEW_NOW = "review_now"
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
    # a plant's own card is a page somebody opened on purpose, so recording redraws it instead of settling it
    # like a digest card, which is about one to-do list. a flag on the payload also covers /today, which no
    # tracker remembers, and the confirmation that arrives on a different message
    from_plant_card: bool = False


class PlantCallback(CallbackData, prefix="plant"):
    action: PlantAction
    plant_id: int = 0


class PhotoHistoryCallback(CallbackData, prefix="hist"):
    """One step through a plant's history. The index is where the card lands, not how far it moves."""

    plant_id: int
    index: int


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
    plant_id: int
    task_types: frozenset[CareTaskType]

    @property
    def reference(self) -> str:
        return build_care_card_reference(self.plant_id, self.task_types)


def build_care_cards(digest: CareDigest, probe_air_by_plant: dict[int, PlantAir] | None = None) -> list[CareCard]:
    """One card per plant, in the order the plants first appear: the photo, every need, and a pair of buttons each."""
    probe_air_by_plant = probe_air_by_plant or {}
    tasks_by_plant: dict[int, list[DueCareTask]] = {}
    for task in digest.tasks:
        tasks_by_plant.setdefault(task.plant_id, []).append(task)
    for tasks in tasks_by_plant.values():
        # the same order every morning, or an edit in place would shuffle the lines the family is used to reading
        tasks.sort(key=lambda task: TASK_TYPE_ORDER.index(task.task_type))

    return [
        CareCard(
            photo_file_id=tasks[0].photo_file_id,
            caption=render_care_card_caption(tasks, probe_air_by_plant.get(plant_id)),
            keyboard=build_care_card_keyboard(tasks),
            plant_id=plant_id,
            task_types=frozenset(task.task_type for task in tasks),
        )
        for plant_id, tasks in tasks_by_plant.items()
    ]


def build_care_card_keyboard(tasks: list[DueCareTask]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for task in tasks:
        # a pair per task: do it, or defer it — there is deliberately no "defer everything"
        builder.row(
            InlineKeyboardButton(
                text=build_task_button_text(task.task_type),
                callback_data=_build_care_card_callback(task).pack(),
                style=SUCCESS_STYLE,
            ),
            InlineKeyboardButton(
                text=CARE_POSTPONE_BUTTON,
                callback_data=ScheduleCallback(
                    action=ScheduleAction.POSTPONE, plant_id=task.plant_id, task_type=task.task_type
                ).pack(),
            ),
        )
    return builder.as_markup()


def build_task_button_text(task_type: CareTaskType) -> str:
    return task_action(task_type).capitalize()


def build_archived_plant_keyboard(plant_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=PLANT_RESTORE_BUTTON,
        callback_data=PlantCallback(action=PlantAction.RESTORE, plant_id=plant_id),
        style=SUCCESS_STYLE,
    )
    return builder.as_markup()


def build_photo_history_keyboard(plant_id: int, index: int, total: int) -> InlineKeyboardMarkup | None:
    """
    One step back, one step forward, and only the ones that lead somewhere.

    the bot api has no carousel: telegram's own «show as carousel» is a send-time option in the clients and
    nothing in the api sets it (checked against bot api 10.3). one photo edited in place is the nearest a bot
    can get to one large frame at a time.
    """
    builder = InlineKeyboardBuilder()
    if index > 0:
        builder.button(
            text=PHOTO_HISTORY_NEWER_BUTTON,
            callback_data=PhotoHistoryCallback(plant_id=plant_id, index=index - 1),
        )
    if index + 1 < total:
        builder.button(
            text=PHOTO_HISTORY_OLDER_BUTTON,
            callback_data=PhotoHistoryCallback(plant_id=plant_id, index=index + 1),
        )
    # a single sitting has nowhere to step, and two dead arrows read as something being broken
    return builder.as_markup() if total > 1 else None


def build_photo_review_retry_keyboard(plant_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=PHOTO_REVIEW_RETRY_BUTTON,
        callback_data=PlantCallback(action=PlantAction.REVIEW_PHOTO, plant_id=plant_id),
    )
    return builder.as_markup()


def build_schedule_remove_keyboard(plant_id: int, task_type: CareTaskType) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=SCHEDULE_REMOVE_BUTTON,
        callback_data=ScheduleCallback(action=ScheduleAction.REMOVE, plant_id=plant_id, task_type=task_type),
        style=DANGER_STYLE,
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


def build_force_care_keyboard(
    plant_id: int, task_type: CareTaskType, from_plant_card: bool = False
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Так, записати",
        callback_data=CareCallback(plant_id=plant_id, task_type=task_type, force=True, from_plant_card=from_plant_card),
        style=SUCCESS_STYLE,
    )
    builder.button(text="Ні", callback_data=PlantCallback(action=PlantAction.OPEN, plant_id=plant_id))
    return builder.as_markup()


def build_plant_list_keyboard(plants: list[PlantSummary]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plant in plants:
        builder.button(
            text=plant.name,
            callback_data=PlantCallback(action=PlantAction.OPEN, plant_id=plant.id),
        )
    builder.adjust(2)
    return builder.as_markup()


def build_plant_card_keyboard(
    card: PlantCard, recorded_task_types: frozenset[CareTaskType] = frozenset()
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for schedule in card.schedules:
        # photo is scheduled like care but recorded by the upload button below, so it gets no record button here
        if schedule.task_type == CareTaskType.PHOTO or schedule.task_type in recorded_task_types:
            continue
        builder.button(
            text=build_task_button_text(schedule.task_type),
            callback_data=CareCallback(plant_id=card.id, task_type=schedule.task_type, from_plant_card=True),
            style=SUCCESS_STYLE,
        )
    builder.adjust(2)

    photo_row = [
        InlineKeyboardButton(
            text="Додати фото",
            callback_data=PlantCallback(action=PlantAction.ADD_PHOTO, plant_id=card.id).pack(),
        )
    ]
    if card.photo_count:
        # the count is of sittings, not of every frame ever taken, because the card behind it steps through
        # one frame per sitting — so the number on the button is exactly how many photos open
        photo_row.append(
            InlineKeyboardButton(
                text=f"Фото ({card.history_photo_count})",
                callback_data=PlantCallback(action=PlantAction.PHOTOS, plant_id=card.id).pack(),
            )
        )
        # the review normally happens on its own when a photo is added; this is for asking again later,
        # which is also the only way to get one for a plant whose photo arrived before the reviews existed
        photo_row.append(
            InlineKeyboardButton(
                text=PHOTO_REVIEW_NOW_BUTTON,
                callback_data=PlantCallback(action=PlantAction.REVIEW_NOW, plant_id=card.id).pack(),
            )
        )
    builder.row(*photo_row)

    builder.row(
        InlineKeyboardButton(
            text="Додати догляд",
            callback_data=ScheduleCallback(action=ScheduleAction.CHOOSE_TASK, plant_id=card.id).pack(),
        ),
        InlineKeyboardButton(
            text="Змінити",
            callback_data=PlantCallback(action=PlantAction.EDIT, plant_id=card.id).pack(),
        ),
        InlineKeyboardButton(
            text="Прибрати",
            callback_data=PlantCallback(action=PlantAction.ARCHIVE, plant_id=card.id).pack(),
            style=DANGER_STYLE,
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="До списку",
            callback_data=PlantCallback(action=PlantAction.LIST).pack(),
        )
    )
    return builder.as_markup()


def find_recorded_task_types(card: PlantCard, keyboard: InlineKeyboardMarkup | None) -> frozenset[CareTaskType]:
    """The tasks whose record button an earlier tap already took off this card, read back from the card itself."""
    if keyboard is None:
        return frozenset()

    offered = {
        CareCallback.unpack(button.callback_data).task_type
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data and button.callback_data.startswith(f"{CareCallback.__prefix__}:")
    }
    return frozenset(schedule.task_type for schedule in card.schedules) - offered


def build_plant_edit_keyboard(card: PlantCard) -> InlineKeyboardMarkup:
    current_values: dict[PlantField, str | None] = {
        PlantField.NAME: card.name,
        PlantField.SPECIES: card.species,
        PlantField.LOCATION: card.location,
        PlantField.ROOM: card.room,
        PlantField.NOTES: card.notes,
        PlantField.TEMPERATURE_RANGE: format_ideal_temperature(card),
        PlantField.HUMIDITY_RANGE: format_ideal_humidity(card),
    }
    builder = InlineKeyboardBuilder()
    for field, label in PLANT_FIELD_LABELS.items():
        builder.row(
            InlineKeyboardButton(
                text=f"{label}: {shorten_for_button(current_values[field])}",
                callback_data=EditPlantCallback(plant_id=card.id, field=field).pack(),
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="Назад",
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
                    text=f"Додати: {task_label(task_type)}",
                    callback_data=_choose_interval_callback(card.id, task_type),
                )
            )
            continue

        current_interval = pluralize_days(schedule.interval_days)
        builder.row(
            InlineKeyboardButton(
                text=f"{task_label(task_type).capitalize()} — раз на {current_interval}",
                callback_data=_choose_interval_callback(card.id, task_type),
            )
        )

        instructions_label = "Інструкція ✓" if schedule.instructions else "Інструкція"
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
                    text="Прибрати",
                    callback_data=ScheduleCallback(
                        action=ScheduleAction.CONFIRM_REMOVE, plant_id=card.id, task_type=task_type
                    ).pack(),
                    style=DANGER_STYLE,
                )
            )
        builder.row(*second_row)

    builder.row(
        InlineKeyboardButton(
            text="Назад",
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
        text="Свій інтервал",
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
    builder.button(text="Свій інтервал", callback_data=NewPlantIntervalCallback(interval_days=CUSTOM_INTERVAL_MARKER))
    builder.adjust(2)
    return builder.as_markup()


def build_archive_confirmation_keyboard(plant_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Так, прибрати",
        callback_data=PlantCallback(action=PlantAction.ARCHIVE_CONFIRM, plant_id=plant_id),
        style=DANGER_STYLE,
    )
    builder.button(text="Ні", callback_data=PlantCallback(action=PlantAction.OPEN, plant_id=plant_id))
    return builder.as_markup()
