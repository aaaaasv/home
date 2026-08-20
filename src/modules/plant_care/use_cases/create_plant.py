from datetime import date, datetime, time

from src.common.constants import CareTaskType
from src.common.domain import Actor
from src.common.exceptions import AlreadyExistsError
from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseActorUseCase
from src.infrastructure.db.models import CareEvent, PlantPhoto
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.commands import CreatePlantCommand
from src.modules.plant_care.domain import PlantCard
from src.modules.plant_care.services.photo_storage import PhotoStorage


class CreatePlantUseCase(BaseActorUseCase):
    def __init__(
        self, uow: UnitOfWork, actor: Actor, household_calendar: HouseholdCalendar, photo_storage: PhotoStorage
    ):
        super().__init__(uow, actor)
        self.household_calendar = household_calendar
        self.photo_storage = photo_storage

    async def __call__(self, command: CreatePlantCommand) -> PlantCard:
        local_photo_path = await self._store_photo_copy(command)
        today = self.household_calendar.today()

        async with self.uow as uow:
            if await uow.plants.retrieve_active_by_name(command.name) is not None:
                raise AlreadyExistsError(f"Plant '{command.name}' already exists")

            plant = await uow.plants.create(
                {
                    "name": command.name,
                    "species": command.species,
                    "location": command.location,
                    "notes": command.notes,
                    "added_by_telegram_user_id": self.actor.telegram_user_id,
                }
            )
            care_events = await self._record_initial_watering(uow, plant.id, command.last_watered_on)
            schedule = await uow.care_schedules.create(
                {
                    "plant_id": plant.id,
                    "task_type": CareTaskType.WATERING,
                    "interval_days": command.watering_interval_days,
                    "next_due_on": self._resolve_first_due_date(command, today),
                    "last_performed_at": care_events[0].performed_at if care_events else None,
                }
            )
            photos = await self._add_photo(uow, plant.id, command, local_photo_path)

            return PlantCard.from_models(plant, [schedule], care_events, photos, today)

    async def _store_photo_copy(self, command: CreatePlantCommand) -> str | None:
        if command.photo is None:
            return None
        return await self.photo_storage.save(command.photo.file_id, command.photo.file_unique_id)

    async def _record_initial_watering(
        self, uow: UnitOfWork, plant_id: int, last_watered_on: date | None
    ) -> list[CareEvent]:
        if last_watered_on is None:
            return []
        event = await uow.care_events.create(
            {
                "plant_id": plant_id,
                "task_type": CareTaskType.WATERING,
                "performed_at": self._as_local_midday(last_watered_on),
                "performed_by_telegram_user_id": self.actor.telegram_user_id,
                "performed_by_display_name": self.actor.display_name,
            }
        )
        return [event]

    async def _add_photo(
        self, uow: UnitOfWork, plant_id: int, command: CreatePlantCommand, local_photo_path: str | None
    ) -> list[PlantPhoto]:
        if command.photo is None:
            return []
        photo = await uow.plant_photos.create(
            {
                "plant_id": plant_id,
                "telegram_file_id": command.photo.file_id,
                "telegram_file_unique_id": command.photo.file_unique_id,
                "local_path": local_photo_path,
                "caption": command.photo.caption,
                "added_by_telegram_user_id": self.actor.telegram_user_id,
                "taken_at": self.household_calendar.now(),
            }
        )
        return [photo]

    def _resolve_first_due_date(self, command: CreatePlantCommand, today: date) -> date:
        if command.last_watered_on is None:
            return today
        return self.household_calendar.next_due_on_after_date(command.last_watered_on, command.watering_interval_days)

    def _as_local_midday(self, day: date) -> datetime:
        return datetime.combine(day, time(hour=12), tzinfo=self.household_calendar.timezone)
