"""Turns this collection's own record into facts a model can answer from."""
from src.bot.handlers.plants.messages import CARE_TASK_LABELS
from src.common.household_calendar import HouseholdCalendar
from src.modules.plant_care.domain import PlantSheet

# enough history to show a rhythm without burying the question in it
RECENT_EVENTS_PER_PLANT = 6


def render_collection_facts(sheets: list[PlantSheet], calendar: HouseholdCalendar) -> str:
    """
    Every living plant as its own short dossier.

    the point of the whole feature is that «чому жовтіє листя Тігла» is answered from what actually happened to
    Тігл — how often it was really watered, in what air — rather than from what the internet says about ficuses.
    """
    if not sheets:
        return ""
    return "Рослини в домі та їхній справжній догляд:\n\n" + "\n\n".join(_describe(sheet, calendar) for sheet in sheets)


def _describe(sheet: PlantSheet, calendar: HouseholdCalendar) -> str:
    lines = [f"— {sheet.name}" + (f" ({sheet.species})" if sheet.species else "")]
    if sheet.location:
        lines.append(f"  місце: {sheet.location}")
    lines.append(f"  у домі {sheet.age_days} дн.")
    if sheet.current_temperature_celsius is not None and sheet.current_humidity_percent is not None:
        lines.append(
            f"  повітря зараз: {sheet.current_temperature_celsius:.0f}°C, "
            f"{sheet.current_humidity_percent:.0f}% вологості"
        )
    if sheet.ideal_temperature_min_celsius is not None:
        lines.append(f"  бажано: {sheet.ideal_temperature_min_celsius:.0f}–{sheet.ideal_temperature_max_celsius:.0f}°C")

    for schedule in sheet.schedules:
        label = CARE_TASK_LABELS[schedule.task_type]
        done = calendar.local_date(schedule.last_performed_at).isoformat() if schedule.last_performed_at else "ніколи"
        lines.append(f"  {label}: раз на {schedule.interval_days} дн., востаннє {done}")

    # the gaps say what the schedule cannot: whether the rhythm on paper is the rhythm in the pot
    if sheet.watering_gaps_days:
        gaps = ", ".join(f"{gap:.0f}" for gap in sheet.watering_gaps_days[-RECENT_EVENTS_PER_PLANT:])
        lines.append(f"  справжні проміжки між поливами, дн.: {gaps}")

    for event in sheet.recent_events[:RECENT_EVENTS_PER_PLANT]:
        moment = calendar.local_date(event.performed_at).isoformat()
        note = f" — {event.note}" if event.note else ""
        lines.append(f"  {moment}: {CARE_TASK_LABELS[event.task_type]}, {event.performed_by_display_name}{note}")

    return "\n".join(lines)
