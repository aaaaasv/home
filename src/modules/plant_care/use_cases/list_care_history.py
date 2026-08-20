from src.common.constants import CARE_HISTORY_PAGE_SIZE, CareTaskType
from src.common.use_case import BaseUseCase
from src.modules.plant_care.domain import CareHistoryEntry


class ListCareHistoryUseCase(BaseUseCase):
    async def __call__(self, limit: int = CARE_HISTORY_PAGE_SIZE) -> list[CareHistoryEntry]:
        async with self.uow as uow:
            recent_events = await uow.care_events.list_recent_with_plants(limit)

        return [
            CareHistoryEntry(
                plant_name=plant.name,
                task_type=CareTaskType(event.task_type),
                performed_at=event.performed_at,
                performed_by_display_name=event.performed_by_display_name,
            )
            for event, plant in recent_events
        ]
