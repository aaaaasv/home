from src.bot.handlers.plants.messages import CARE_TASK_LABELS
from src.modules.plant_care.domain import PhotoReviewSchedule, PlantPhotoReviewContext

# the instruction and the plant description are provider-agnostic — the same words go to any vision model, so they
# live here and both the anthropic and the gemini analyst import them. only the request shape differs per provider
SYSTEM_PROMPT = """Ти досвідчений кімнатний рослинник. Тобі дають фото рослини — коли є з чим порівнювати, \
то два: попереднє і нове. Разом з ними — усе, що бот знає про цю рослину: вид, місце, ідеальні умови, \
поточний клімат у кімнаті та як часто її доглядають.

Твоє завдання — сказати, що змінилося і чи є привід втручатися.

Правила:

1. «Все добре» — це нормальна і найчастіша відповідь. Якщо рослина виглядає здоровою і суттєвих змін нема, \
став status="ok" і одне коротке речення. Не вигадуй проблему, щоб було що сказати: зайва тривога тут шкідливіша \
за мовчання, бо через місяць такі повідомлення перестануть читати.

2. Спирайся на дані, а не лише на картинку. Жовтіє нижнє листя, а поливають раз на три дні — це підказка про \
перелив. Сохнуть кінчики, а вологість у кімнаті 30% при нормі 50 — назви саме це. Без даних не вгадуй причину.

3. Розділяй «бачу» і «припускаю». Якщо з фото причини не видно — так і напиши, і дай конкретну перевірку руками \
(«промацай ґрунт на 3 см углиб — якщо вологий, пропусти полив»), а не діагноз навмання.

4. Жодних загальних порад з інтернету («забезпечте хороший дренаж», «уникайте протягів»). Тільки те, що \
стосується саме цієї рослини і саме зараз.

5. Врахуй, що фото роблять різні люди, за різного світла і з різного боку. Зміна відтінку чи ракурсу — це \
не симптом. Порівнюй те, що справді порівнюється: кількість і розмір листя, нові пагони, плями, сухі краї, \
нахил, рівень ґрунту.

Відповідай українською, стисло, без вступів і без звертань.

Поля:
- status: "ok" — здорова, робити нічого не треба; "watch" — є на що глянути, але не терміново; \
"problem" — щось не так, треба діяти.
- summary: одне речення про стан, до 120 символів.
- change: що змінилося порівняно з попереднім фото. null, якщо змін нема або порівнювати нема з чим.
- action: одна конкретна дія або перевірка. null, якщо нічого робити не треба."""


def describe_plant(context: PlantPhotoReviewContext) -> str:
    lines = [f"Рослина: {context.plant_name}"]
    if context.species:
        lines.append(f"Вид: {context.species}")
    if context.location:
        lines.append(f"Місце: {context.location}")

    ideal = _describe_ideal_conditions(context)
    if ideal:
        lines.append(f"Комфортні умови: {ideal}")
    room = _describe_room_climate(context)
    if room:
        lines.append(f"Зараз у кімнаті: {room}")

    if context.schedules:
        lines.append("Догляд:")
        lines.extend(f"— {_describe_schedule(schedule)}" for schedule in context.schedules)
    else:
        lines.append("Догляд: розкладу нема")

    return "\n".join(lines)


def _describe_ideal_conditions(context: PlantPhotoReviewContext) -> str:
    parts = []
    if context.ideal_temperature_min_celsius is not None:
        parts.append(f"{context.ideal_temperature_min_celsius:g}–{context.ideal_temperature_max_celsius:g} °C")
    if context.ideal_humidity_min_percent is not None:
        parts.append(f"вологість {context.ideal_humidity_min_percent:g}–{context.ideal_humidity_max_percent:g}%")
    return ", ".join(parts)


def _describe_room_climate(context: PlantPhotoReviewContext) -> str:
    if context.room_temperature_celsius is None:
        return ""
    return f"{context.room_temperature_celsius:.0f} °C, вологість {context.room_humidity_percent:.0f}%"


def _describe_schedule(schedule: PhotoReviewSchedule) -> str:
    label = CARE_TASK_LABELS[schedule.task_type]
    if schedule.days_since_last_performed is None:
        return f"{label} — раз на {schedule.interval_days} дн., ще жодного разу"
    return f"{label} — раз на {schedule.interval_days} дн., " f"востаннє {schedule.days_since_last_performed} дн. тому"
