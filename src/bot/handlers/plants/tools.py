"""The plant record as something the assistant may write to, when the family tells it to in plain words."""
import logging
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from src.bot.handlers.plants.messages import CARE_TASK_LABELS
from src.common.config import Settings
from src.common.constants import CareTaskType, PlantField
from src.common.exceptions import DoesNotExistError
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.commands import SetCareInstructionsCommand, UpdatePlantCommand
from src.modules.plant_care.use_cases.set_care_instructions import SetCareInstructionsUseCase
from src.modules.plant_care.use_cases.update_plant import UpdatePlantUseCase

logger = logging.getLogger(__name__)

# only the card's prose. a wrong sentence here costs a sentence, while an interval or a care event would quietly
# move when the family is reminded and what the photo review believes already happened
WRITABLE_FIELDS: dict[str, str] = {
    PlantField.SPECIES: "вид",
    PlantField.LOCATION: "місце",
    PlantField.ROOM: "кімната",
    PlantField.NOTES: "нотатки",
}

# a declined name has to find its plant: «сорт принцеси» is about Принцеса. so the two may differ in their
# endings and nowhere else — Кроко does not answer to Кротон, which shares only three letters and keeps three
LONGEST_ENDING = 2
SHORTEST_SHARED_STEM = 3

PLANT_TOOLS: list[dict[str, Any]] = [
    {
        "name": "update_plant_card",
        "description": (
            "Записати або стерти одне текстове поле на картці рослини. "
            "Користуйся, коли тебе просять щось виправити, дописати чи прибрати з опису рослини. "
            "value=null стирає поле. Пиши тільки те, що тобі сказали — не вигадуй і не доповнюй від себе."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "plant": {"type": "string", "description": "Як рослину звуть удома, наприклад «Принцеса»."},
                "field": {
                    "type": "string",
                    "enum": list(WRITABLE_FIELDS),
                    "description": (
                        "species — біноміальна латина й сорт; location — де стоїть, прозою; "
                        "room — кімната, за повітрям якої її судять, рівно як названа в сенсорах; "
                        "notes — вільні нотатки про цю рослину."
                    ),
                },
                "value": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "description": "Новий текст, або null, щоб стерти поле.",
                },
            },
            "required": ["plant", "field", "value"],
            "additionalProperties": False,
        },
    },
    {
        "name": "set_plant_care_instructions",
        "description": (
            "Записати або стерти інструкцію до одного завдання догляду за рослиною — те, що видно "
            "під рядком завдання на картці. Не змінює ні інтервал, ні дату наступного разу."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "plant": {"type": "string", "description": "Як рослину звуть удома."},
                "task_type": {"type": "string", "enum": [task.value for task in CareTaskType]},
                "instructions": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "description": "Нова інструкція, або null, щоб стерти її.",
                },
            },
            "required": ["plant", "task_type", "instructions"],
            "additionalProperties": False,
        },
    },
]


class PlantTools:
    """
    Lets the assistant write the plant card the family is talking about, instead of telling them where to tap.

    it writes immediately and answers with what the field held before, because that sentence is the whole
    safety story: the family reads «було … стало …» in the reply and says «поверни» if it is wrong. nothing
    here touches a schedule or a care event, so the worst a confused write can do is put a wrong sentence on
    a card — never silently move when a plant is watered.
    """

    def __init__(self, uow_factory: Callable[[], UnitOfWork], settings: Settings):
        self.uow_factory = uow_factory
        self.settings = settings

    @property
    def definitions(self) -> list[dict[str, Any]]:
        return PLANT_TOOLS

    async def run(self, name: str, arguments: dict[str, Any]) -> str:
        if name == "update_plant_card":
            return await self.update_plant_card(
                arguments.get("plant", ""), arguments.get("field", ""), arguments.get("value")
            )
        if name == "set_plant_care_instructions":
            return await self.set_plant_care_instructions(
                arguments.get("plant", ""), arguments.get("task_type", ""), arguments.get("instructions")
            )
        logger.warning("The assistant asked for a plant tool that does not exist: %s", name)
        return "Такого інструмента немає."

    async def update_plant_card(self, spoken_name: str, field: str, value: str | None) -> str:
        if field not in WRITABLE_FIELDS:
            return f"Поле «{field}» я не змінюю. Можу: {', '.join(WRITABLE_FIELDS.values())}."

        plant, refusal = await self._find_plant(spoken_name)
        if plant is None:
            return refusal

        if field == PlantField.ROOM and value is not None:
            known_rooms = set(self.settings.room_by_sensor.values())
            if value not in known_rooms:
                return (
                    f"Кімнати «{value}» немає серед тих, де стоять датчики, а за ними цю рослину й судять. "
                    f"Є: {', '.join(sorted(known_rooms)) or 'жодної'}."
                )

        was = getattr(plant, field)
        if was == value:
            return f"{plant.name}: тут уже саме це й записано, нічого не міняв."

        try:
            command = UpdatePlantCommand(plant_id=plant.id, **{field: value})
        except ValidationError:
            return f"Не записав: для поля «{WRITABLE_FIELDS[field]}» цей текст задовгий."

        await UpdatePlantUseCase(uow=self.uow_factory())(command)
        logger.info("The assistant wrote %s on plant %s", field, plant.id)
        return self._describe(plant.name, WRITABLE_FIELDS[field], was, value)

    async def set_plant_care_instructions(self, spoken_name: str, task_type: str, instructions: str | None) -> str:
        try:
            task = CareTaskType(task_type)
        except ValueError:
            return f"Завдання «{task_type}» не існує."

        plant, refusal = await self._find_plant(spoken_name)
        if plant is None:
            return refusal

        try:
            command = SetCareInstructionsCommand(plant_id=plant.id, task_type=task, instructions=instructions)
        except ValidationError:
            return "Не записав: інструкція задовга."

        async with self.uow_factory() as uow:
            schedule = await uow.care_schedules.retrieve_for_plant(plant.id, task)
        if schedule is None:
            return f"{plant.name}: немає завдання «{CARE_TASK_LABELS[task]}», тож і інструкції до нього."

        try:
            await SetCareInstructionsUseCase(uow=self.uow_factory())(command)
        except DoesNotExistError:
            return f"{plant.name}: немає завдання «{CARE_TASK_LABELS[task]}», тож і інструкції до нього."

        logger.info("The assistant wrote the %s instructions on plant %s", task.value, plant.id)
        return self._describe(plant.name, CARE_TASK_LABELS[task], schedule.instructions, instructions)

    async def _find_plant(self, spoken_name: str):
        """The plant, or the sentence to answer with instead — the model speaks names, not identifiers."""
        async with self.uow_factory() as uow:
            plants = await uow.plants.list_active()

        matched = match_plant_name(spoken_name, [plant.name for plant in plants])
        if not matched:
            known = ", ".join(plant.name for plant in plants) or "жодної"
            return None, f"Не знаходжу рослину «{spoken_name}». Є: {known}."
        if len(matched) > 1:
            return None, f"«{spoken_name}» підходить і до {', і до '.join(matched)} — уточни, про яку йдеться."

        return next(plant for plant in plants if plant.name == matched[0]), ""

    def _describe(self, name: str, label: str, was: str | None, became: str | None) -> str:
        """What changed, in the words the family reads back before deciding whether to undo it."""
        if became is None:
            return f"Стер. {name}, {label}: було «{was}», тепер порожньо."
        if was is None:
            return f"Записав. {name}, {label}: було порожньо, стало «{became}»."
        return f"Записав. {name}, {label}: було «{was}», стало «{became}»."


def match_plant_name(spoken_name: str, names: list[str]) -> list[str]:
    """
    Every name a spoken one could mean, because ukrainian declines them and the model repeats what it heard.

    «сорт принцеси» has to reach Принцеса, so an exact hit wins outright and anything else falls back to the
    stem the two share. two matches are returned as two: asking which one is right beats writing to a namesake.
    """
    wanted = spoken_name.strip().casefold()
    if not wanted:
        return []

    exact = [name for name in names if name.casefold() == wanted]
    if exact:
        return exact
    return [name for name in names if _shares_a_stem(name.casefold(), wanted)]


def _shares_a_stem(name: str, wanted: str) -> bool:
    shared = 0
    for name_character, wanted_character in zip(name, wanted):
        if name_character != wanted_character:
            break
        shared += 1
    if shared < SHORTEST_SHARED_STEM:
        return False
    return len(name) - shared <= LONGEST_ENDING and len(wanted) - shared <= LONGEST_ENDING
