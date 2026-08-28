from src.common.constants import CareTaskType
from src.common.domain import Actor
from src.common.exceptions import DoesNotExistError
from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseActorUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.commands import AddPlantPhotoCommand
from src.modules.plant_care.domain import PlantPhotoDetails
from src.modules.plant_care.services.photo_storage import PhotoStorage


class AddPlantPhotoUseCase(BaseActorUseCase):
    def __init__(
        self, uow: UnitOfWork, actor: Actor, photo_storage: PhotoStorage, household_calendar: HouseholdCalendar
    ):
        super().__init__(uow, actor)
        self.photo_storage = photo_storage
        self.household_calendar = household_calendar

    async def __call__(self, command: AddPlantPhotoCommand) -> PlantPhotoDetails:
        local_path = await self.photo_storage.save(command.photo.file_id, command.photo.file_unique_id)

        async with self.uow as uow:
            plant = await uow.plants.retrieve_active(command.plant_id)
            if plant is None:
                raise DoesNotExistError(f"Plant {command.plant_id} not found")

            photo = await uow.plant_photos.create(
                {
                    "plant_id": command.plant_id,
                    "telegram_file_id": command.photo.file_id,
                    "telegram_file_unique_id": command.photo.file_unique_id,
                    "local_path": local_path,
                    "caption": command.photo.caption,
                    "frame": command.frame.value,
                    "added_by_telegram_user_id": self.actor.telegram_user_id,
                    "taken_at": command.taken_at,
                }
            )
            await self._reschedule_next_photo(command)
            return PlantPhotoDetails.from_photo(photo)

    async def _reschedule_next_photo(self, command: AddPlantPhotoCommand) -> None:
        # any photo counts, however it was added — the next reminder is always a full interval after the latest one
        schedule = await self.uow.care_schedules.retrieve_for_plant(command.plant_id, CareTaskType.PHOTO)
        if schedule is None:
            return

        await self.uow.care_schedules.update(
            schedule.id,
            {
                "last_performed_at": command.taken_at,
                "next_due_on": self.household_calendar.next_due_on(command.taken_at, schedule.interval_days),
            },
        )
