"""What a plant's standing care card is about, written into the one string the message tracker keeps for it."""
from collections.abc import Iterable
from typing import NamedTuple

from src.common.constants import CareTaskType

TASK_TYPE_ORDER = tuple(CareTaskType)


class CareCardReference(NamedTuple):
    plant_id: int
    task_types: frozenset[CareTaskType]


def build_care_card_reference(plant_id: int, task_types: Iterable[CareTaskType]) -> str:
    """
    The plant id and the needs its card lists, as "12:5" — the reference column holds 32 characters.

    the needs are a bit mask over the task types, so the next digest can tell a card that merely lost a need
    from one that gained a need it never announced. an empty mask is a settled card: a receipt with nothing due.
    """
    mask = sum(1 << TASK_TYPE_ORDER.index(task_type) for task_type in set(task_types))
    return f"{plant_id}:{mask}"


def parse_care_card_reference(reference: str | None) -> CareCardReference | None:
    """None for a reference this format did not write — yesterday's one-card-per-task rows read as "watering:5"."""
    plant_id, separator, mask = (reference or "").partition(":")
    if not separator or not plant_id.isdecimal() or not mask.isdecimal():
        return None
    return CareCardReference(
        plant_id=int(plant_id),
        task_types=frozenset(task_type for index, task_type in enumerate(TASK_TYPE_ORDER) if int(mask) & (1 << index)),
    )
