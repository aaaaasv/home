"""What the plant care module says."""

from src.common.constants import (
    CARE_INSTRUCTIONS_MAX_LENGTH,
    MAXIMUM_CARE_INTERVAL_DAYS,
    MINIMUM_CARE_INTERVAL_DAYS,
    CareTaskType,
    ClimateDimension,
    ClimateStatus,
    PlantField,
    PlantPhotoReviewStatus,
)

CARE_TASK_LABELS: dict[CareTaskType, str] = {
    CareTaskType.WATERING: "полив",
    CareTaskType.FERTILIZING: "добриво",
    CareTaskType.FLUSH: "промивання",
    CareTaskType.REPOTTING: "пересадка",
    CareTaskType.ROTATING: "повертання",
    CareTaskType.PHOTO: "фото",
}

CARE_TASK_EMOJI: dict[CareTaskType, str] = {
    CareTaskType.WATERING: "💧",
    CareTaskType.FERTILIZING: "🌱",
    CareTaskType.FLUSH: "🚿",
    CareTaskType.REPOTTING: "🪴",
    CareTaskType.ROTATING: "🔄",
    CareTaskType.PHOTO: "📸",
}

# on a button the label must read as a done action — the impersonal -но/-то form (як «Збережено»), not the noun
CARE_TASK_ACTIONS: dict[CareTaskType, str] = {
    CareTaskType.WATERING: "полито",
    CareTaskType.FERTILIZING: "підживлено",
    CareTaskType.FLUSH: "промито",
    CareTaskType.REPOTTING: "пересаджено",
    CareTaskType.ROTATING: "повернуто",
    # the odd one out: this button opens the upload flow, so it names the action still to be done
    CareTaskType.PHOTO: "сфотографувати",
}

OVERDUE_EMOJI = "🔴"
PLANT_EMOJI = "🪴"

NO_PLANTS = "Поки що жодної рослини. Додай першу: /add"
NOTHING_DUE = "✨ Сьогодні все доглянуто."
NO_HISTORY = "Історія порожня."
NO_PHOTOS = "У цієї рослини ще немає фото."
INVALID_INTERVAL = f"Потрібне число від {MINIMUM_CARE_INTERVAL_DAYS} до {MAXIMUM_CARE_INTERVAL_DAYS}."

ADD_PLANT_ASK_NAME = "Як назвемо рослину?"
ADD_PLANT_NAME_TOO_LONG = "Задовга назва — до 64 символів."
ADD_PLANT_ASK_PHOTO = "Надішли одне фото 📸\n\n/skip — пропустити"
ADD_PLANT_ASK_INTERVAL = "Як часто поливати?"
ADD_PLANT_ASK_CUSTOM_INTERVAL = (
    f"Раз на скільки днів поливати? Надішли число від {MINIMUM_CARE_INTERVAL_DAYS} до {MAXIMUM_CARE_INTERVAL_DAYS}."
)
ADD_PLANT_IDENTIFYING = "🔎 Дивлюсь, що це…"
ADD_PLANT_IDENTIFICATION_INTRO = "Схоже на це:"
ADD_PLANT_IDENTIFICATION_UNSURE = "Не впізнаю за цим фото — розкажи сам."

ADD_PLANT_EXPECTS_PHOTO = "Надішли саме фото або /skip."
ADD_PLANT_EXPECTS_TEXT = "Надішли текст або /skip."

ADD_PHOTO_ASK_PHOTO = (
    "Надішли фото 📸\n"
    "Перше — загальний кадр з того самого боку, що й минулого разу: саме його порівнюють між собою.\n"
    "Далі можна крупні плани листя, скільки треба.\n\n"
    "/cancel — скасувати"
)
CARE_POSTPONE_BUTTON = "⏳ нагадати через {days}"
# a skippable task (fertilizing, photo) defers a whole cycle, so its button says "skip", not "in N days"
CARE_SKIP_BUTTON = "⏭ пропустити"
CARE_POSTPONED_TOAST = "Нагадаю {when}"

# the card stays after recording instead of vanishing — with the record button gone it no longer invites a
# second watering, and it is the only place an accidental tap can be taken back the moment it happens
CARE_UNDO_BUTTON = "↩️ скасувати"
CARE_RECORDED_CARD = "✅ <b>{plant}</b> — {emoji} {action}\n<i>{who}, {time}</i>"
CARE_UNDONE_TOAST = "Запис скасовано"

# removing a schedule is the one destructive action with nothing to undo it, and the button is a bare "➖"
# next to the harmless one — so it asks first, and names the instruction it is about to take with it
SCHEDULE_REMOVE_CONFIRM = "Прибрати {task} у «{plant}»?"
SCHEDULE_REMOVE_CONFIRM_INSTRUCTIONS = "\n\n⚠️ Інструкція до цього догляду теж зникне."
SCHEDULE_REMOVE_BUTTON = "Так, прибрати"

PHOTO_ADDED = "📸 Фото додано."
PHOTOS_ADDED = "📸 Додано {count} кадри. Перший — для порівняння, решта в зібранні."

PHOTO_REVIEW_IN_PROGRESS = "🔎 Дивлюсь, що змінилось…"
PHOTO_REVIEW_CHANGE_LABEL = "Зміни"
PHOTO_REVIEW_ACTION_LABEL = "Що зробити"

PHOTO_REVIEW_STATUS_EMOJI: dict[PlantPhotoReviewStatus, str] = {
    PlantPhotoReviewStatus.OK: "✅",
    PlantPhotoReviewStatus.WATCH: "👀",
    PlantPhotoReviewStatus.PROBLEM: "⚠️",
}

PLANT_FIELD_LABELS: dict[PlantField, str] = {
    PlantField.NAME: "Назва",
    PlantField.SPECIES: "Вид",
    PlantField.LOCATION: "Місце",
    PlantField.NOTES: "Нотатка",
    PlantField.TEMPERATURE_RANGE: "🌡 Температура",
    PlantField.HUMIDITY_RANGE: "💧 Вологість",
}

ASK_EDIT_FIELD = "Що змінити?"
EDIT_FIELD_PROMPTS: dict[PlantField, str] = {
    PlantField.NAME: "Надішли нову назву.",
    PlantField.SPECIES: "Що це за вид? Наприклад: <i>Monstera deliciosa</i>\n\n/clear — прибрати",
    PlantField.LOCATION: "Де вона стоїть? Наприклад: <i>спальня, підвіконня</i>\n\n/clear — прибрати",
    PlantField.NOTES: "Що варто пам'ятати про цю рослину?\n\n/clear — прибрати",
    PlantField.TEMPERATURE_RANGE: "Комфортна температура, °C? Наприклад: <i>18-27</i>\n\n/clear — прибрати",
    PlantField.HUMIDITY_RANGE: "Комфортна вологість, %? Наприклад: <i>50-70</i>\n\n/clear — прибрати",
}
EDIT_VALUE_TOO_LONG = "Задовге значення — до {max_length} символів."
CLIMATE_RANGE_INVALID = "Не зрозумів. Надішли діапазон «мін-макс», наприклад <i>18-27</i>."
NAME_CANNOT_BE_CLEARED = "Назву прибрати не можна."

ASK_TASK_TYPE = "Що з доглядом?"
ASK_TASK_INTERVAL = "Раз на скільки днів?"
ASK_CUSTOM_TASK_INTERVAL = (
    f"Раз на скільки днів? Надішли число від {MINIMUM_CARE_INTERVAL_DAYS} до {MAXIMUM_CARE_INTERVAL_DAYS}."
)
WATERING_CANNOT_BE_REMOVED = "Полив прибрати не можна."
ASK_CARE_INSTRUCTIONS = "Надішли інструкцію для цього догляду — як саме робити, скільки води тощо.\n\n/clear — прибрати"
CARE_INSTRUCTIONS_TOO_LONG = f"Задовга інструкція — до {CARE_INSTRUCTIONS_MAX_LENGTH} символів."
ARCHIVE_CONFIRM = "Точно прибрати <b>{plant_name}</b> зі списку? Історія та фото збережуться."
PLANT_ARCHIVED = "🗑 <b>{plant_name}</b> прибрано зі списку."
# archiving hides the plant with its schedules, photos and history, and nothing else brings them back
PLANT_RESTORE_BUTTON = "↩️ повернути"
PLANT_RESTORED = "🪴 <b>{plant_name}</b> повернуто до списку."

CARE_RECORDED_TOAST = "Записав ✅"

# one standing card per uncomfortable plant, so a line names its own plant; fires on a crossing that held for a
# full day, not on a number — a heated flat is simply dry all winter
CLIMATE_PROBLEM_LINES: dict[tuple[ClimateDimension, ClimateStatus], str] = {
    (ClimateDimension.HUMIDITY, ClimateStatus.TOO_LOW): "💧 <b>{plant}</b> — сухо: {value}%, треба {low}–{high}%",
    (ClimateDimension.HUMIDITY, ClimateStatus.TOO_HIGH): "💦 <b>{plant}</b> — волого: {value}%, треба {low}–{high}%",
    (
        ClimateDimension.TEMPERATURE,
        ClimateStatus.TOO_LOW,
    ): "🥶 <b>{plant}</b> — холодно: {value}°, треба {low}–{high}°",
    (
        ClimateDimension.TEMPERATURE,
        ClimateStatus.TOO_HIGH,
    ): "🔥 <b>{plant}</b> — жарко: {value}°, треба {low}–{high}°",
}
# posted once, when every dimension is back in range and the plant's discomfort card is deleted
PLANT_COMFORT_RESTORED = "✅ <b>{plant}</b> — знову комфортно"
