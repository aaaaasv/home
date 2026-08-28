"""How plants, their care cards and their comfort cards render."""
import math
from datetime import datetime
from html import escape

from src.bot.formatting import format_due, format_moment, pluralize_days
from src.bot.handlers.plants.messages import (
    ADD_PLANT_IDENTIFICATION_INTRO,
    CARE_RECORDED_CARD,
    CARE_TASK_ACTIONS,
    CARE_TASK_EMOJI,
    CARE_TASK_LABELS,
    CLIMATE_PROBLEM_LINES,
    OVERDUE_EMOJI,
    PHOTO_REVIEW_ACTION_LABEL,
    PHOTO_REVIEW_CHANGE_LABEL,
    PHOTO_REVIEW_STATUS_EMOJI,
    PLANT_COMFORT_RESTORED,
    PLANT_EMOJI,
    SCHEDULE_REMOVE_CONFIRM,
    SCHEDULE_REMOVE_CONFIRM_INSTRUCTIONS,
)
from src.common.constants import CareTaskType, ClimateStatus
from src.common.household_calendar import HouseholdCalendar
from src.modules.plant_care.domain import (
    CareHistoryEntry,
    CareRecord,
    CareScheduleDetails,
    ClimateProblem,
    DueCareTask,
    PlantCard,
    PlantComfortChange,
    PlantIdentification,
    PlantPhotoReview,
    PlantSummary,
)


def task_label(task_type: CareTaskType) -> str:
    return CARE_TASK_LABELS[task_type]


def task_emoji(task_type: CareTaskType) -> str:
    return CARE_TASK_EMOJI[task_type]


def task_action(task_type: CareTaskType) -> str:
    return CARE_TASK_ACTIONS[task_type]


def render_care_card_caption(task: DueCareTask) -> str:
    header_emoji = OVERDUE_EMOJI if task.overdue_days > 0 else PLANT_EMOJI
    lines = [f"{header_emoji} <b>{escape(task.plant_name)}</b>"]
    task_line = f"{task_emoji(task.task_type)} {task_label(task.task_type)}"
    if task.overdue_days > 0:
        task_line += f" <i>(прострочено {pluralize_days(task.overdue_days)})</i>"
    lines.append(task_line)
    if task.instructions:
        lines.append(f"<blockquote expandable>{escape(task.instructions)}</blockquote>")
    return "\n".join(lines)


def render_plant_discomfort_card(change: PlantComfortChange) -> str:
    return "\n".join(_render_climate_problem(problem, change.plant_name) for problem in change.problems)


def render_plant_comfort_restored(plant_name: str) -> str:
    return PLANT_COMFORT_RESTORED.format(plant=escape(plant_name))


def _render_climate_problem(problem: ClimateProblem, plant_name: str) -> str:
    # round toward the deviation (down when too low, up when too high) so the number never lands inside the range
    if problem.status == ClimateStatus.TOO_LOW:
        value = math.floor(problem.value)
    else:
        value = math.ceil(problem.value)
    return CLIMATE_PROBLEM_LINES[(problem.dimension, problem.status)].format(
        plant=escape(plant_name),
        value=value,
        low=_trim_number(problem.ideal_min),
        high=_trim_number(problem.ideal_max),
    )


def _trim_number(number: float) -> str:
    return f"{number:g}"


def format_ideal_temperature(card: PlantCard) -> str | None:
    if card.ideal_temperature_min_celsius is None or card.ideal_temperature_max_celsius is None:
        return None
    return f"{_trim_number(card.ideal_temperature_min_celsius)}–{_trim_number(card.ideal_temperature_max_celsius)}°"


def format_ideal_humidity(card: PlantCard) -> str | None:
    if card.ideal_humidity_min_percent is None or card.ideal_humidity_max_percent is None:
        return None
    return f"{_trim_number(card.ideal_humidity_min_percent)}–{_trim_number(card.ideal_humidity_max_percent)}%"


def _render_ideal_climate_line(card: PlantCard) -> str | None:
    temperature = format_ideal_temperature(card)
    humidity = format_ideal_humidity(card)
    parts = []
    if temperature:
        parts.append(f"🌡 {temperature}")
    if humidity:
        parts.append(f"💧 {humidity}")
    if not parts:
        return None
    return "   ".join(parts)


def render_plant_list(plants: list[PlantSummary]) -> str:
    lines = ["🪴 <b>Рослини</b>", ""]
    for plant in plants:
        header = f"{PLANT_EMOJI} <b>{escape(plant.name)}</b>"
        if plant.location:
            header += f" · <i>{escape(plant.location)}</i>"
        lines.append(header)
        lines.extend(f"   {_render_schedule_line(schedule)}" for schedule in plant.schedules)
        lines.append("")
    return "\n".join(lines).strip()


def render_plant_card(card: PlantCard, calendar: HouseholdCalendar) -> str:
    lines = [f"{PLANT_EMOJI} <b>{escape(card.name)}</b>"]
    if card.species:
        lines.append(f"🔬 <i>{escape(card.species)}</i>")
    if card.location:
        lines.append(f"📍 {escape(card.location)}")
    if card.notes:
        lines.append(f"📝 {escape(card.notes)}")

    ideal_climate = _render_ideal_climate_line(card)
    if ideal_climate:
        lines.append(ideal_climate)

    lines.extend(["", "<b>Догляд</b>"])
    for schedule in card.schedules:
        lines.append(_render_schedule_line(schedule))
        if schedule.instructions:
            # each schedule's how-to as its own collapsed block, so watering, feeding etc. read independently
            lines.append(f"<blockquote expandable>{escape(schedule.instructions)}</blockquote>")

    if card.recent_events:
        # history is reference, not the point of the card — collapse it so the card stays scannable
        history = "\n".join(
            [
                "<b>Останні дії</b>",
                *(
                    f"{format_moment(event.performed_at, calendar)} — {task_label(event.task_type)}"
                    f" · {escape(event.performed_by_display_name)}"
                    for event in card.recent_events
                ),
            ]
        )
        lines.extend(["", f"<blockquote expandable>{history}</blockquote>"])

    if card.photo_count:
        lines.extend(["", f"📸 фото: {card.photo_count}"])

    return "\n".join(lines)


def render_recent_care_warning(
    plant_name: str,
    task_type: CareTaskType,
    performed_at: datetime,
    performed_by_display_name: str,
    calendar: HouseholdCalendar,
) -> str:
    return (
        f"⚠️ <b>{escape(plant_name)}</b> вже мала догляд «{task_label(task_type)}»\n"
        f"👤 {escape(performed_by_display_name)} · {format_moment(performed_at, calendar)}\n\n"
        f"Записати ще раз?"
    )


def render_care_history(entries: list[CareHistoryEntry], calendar: HouseholdCalendar) -> str:
    lines = ["🗓 <b>Останні дії</b>", ""]
    lines.extend(
        f"{task_emoji(entry.task_type)} <b>{escape(entry.plant_name)}</b> — {task_label(entry.task_type)}\n"
        f"   {format_moment(entry.performed_at, calendar)} · {escape(entry.performed_by_display_name)}"
        for entry in entries
    )
    return "\n".join(lines)


def _render_schedule_line(schedule: CareScheduleDetails) -> str:
    emoji = OVERDUE_EMOJI if schedule.overdue_days > 0 else task_emoji(schedule.task_type)
    return (
        f"{emoji} {task_label(schedule.task_type)} — раз на {pluralize_days(schedule.interval_days)}"
        f" · {format_due(schedule.days_until_due)}"
    )


def render_plant_photo_review(review: PlantPhotoReview) -> str:
    lines = [f"{PHOTO_REVIEW_STATUS_EMOJI[review.status]} {escape(review.summary)}"]
    details = []
    if review.change:
        details.append(f"<i>{PHOTO_REVIEW_CHANGE_LABEL}:</i> {escape(review.change)}")
    if review.action:
        details.append(f"<i>{PHOTO_REVIEW_ACTION_LABEL}:</i> {escape(review.action)}")
    if details:
        lines.append("")
        lines.extend(details)
    return "\n".join(lines)


def render_recorded_care(record: CareRecord, performed_at: datetime, calendar: HouseholdCalendar) -> str:
    return CARE_RECORDED_CARD.format(
        plant=escape(record.plant_name),
        emoji=task_emoji(record.task_type),
        action=task_action(record.task_type),
        who=escape(record.performed_by_display_name),
        time=f"{performed_at.astimezone(calendar.timezone):%H:%M}",
    )


def render_schedule_remove_confirm(plant_name: str, schedule: CareScheduleDetails) -> str:
    question = SCHEDULE_REMOVE_CONFIRM.format(task=task_label(schedule.task_type), plant=escape(plant_name))
    if schedule.instructions:
        return question + SCHEDULE_REMOVE_CONFIRM_INSTRUCTIONS
    return question


def render_plant_identification(identification: PlantIdentification) -> str:
    """What the model made of the photo, with every blank left visibly blank rather than filled with a guess."""
    title = identification.common_name or identification.species
    lines = [ADD_PLANT_IDENTIFICATION_INTRO, "", f"<b>{escape(title)}</b>"]
    if identification.species is not None and identification.common_name is not None:
        lines.append(f"<i>{escape(identification.species)}</i>")
    if identification.watering_interval_days is not None:
        lines.append(f"\n💧 поливати раз на {identification.watering_interval_days} дн.")
    if identification.care_notes is not None:
        lines.append(f"\n{escape(identification.care_notes)}")
    return "\n".join(lines)
