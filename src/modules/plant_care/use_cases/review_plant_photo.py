from src.common.constants import CareTaskType
from src.common.exceptions import DoesNotExistError
from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.models import CareSchedule, Plant, PlantPhoto, RoomClimateReading
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.domain import PhotoReviewSchedule, PlantPhotoReview, PlantPhotoReviewContext
from src.modules.plant_care.services.photo_analyst import PhotoAnalyst


class ReviewPlantPhotoUseCase(BaseUseCase):
    def __init__(self, uow: UnitOfWork, household_calendar: HouseholdCalendar, photo_analyst: PhotoAnalyst):
        super().__init__(uow)
        self.household_calendar = household_calendar
        self.photo_analyst = photo_analyst

    async def __call__(self, plant_id: int) -> PlantPhotoReview | None:
        async with self.uow as uow:
            plant = await uow.plants.retrieve_active(plant_id)
            if plant is None:
                raise DoesNotExistError(f"Plant {plant_id} not found")

            photos = await uow.plant_photos.list_by_plant_id(plant_id)
            schedules = await uow.care_schedules.list_by_plant_id(plant_id)
            room_climate = await uow.room_climate_readings.retrieve_latest()

        context = self._build_context(plant, photos, schedules, room_climate)
        if context is None:
            return None

        return await self.photo_analyst.review_photo(context)

    def _build_context(
        self,
        plant: Plant,
        photos: list[PlantPhoto],
        schedules: list[CareSchedule],
        room_climate: RoomClimateReading | None,
    ) -> PlantPhotoReviewContext | None:
        current = photos[-1]
        # a photo whose download failed has no local copy, and there is nothing to send without one
        if current.local_path is None:
            return None

        previous = next((photo for photo in reversed(photos[:-1]) if photo.local_path is not None), None)
        return PlantPhotoReviewContext(
            plant_name=plant.name,
            species=plant.species,
            location=plant.location,
            ideal_temperature_min_celsius=plant.ideal_temperature_min_celsius,
            ideal_temperature_max_celsius=plant.ideal_temperature_max_celsius,
            ideal_humidity_min_percent=plant.ideal_humidity_min_percent,
            ideal_humidity_max_percent=plant.ideal_humidity_max_percent,
            room_temperature_celsius=room_climate.temperature_celsius if room_climate else None,
            room_humidity_percent=room_climate.relative_humidity_percent if room_climate else None,
            # the photo schedule itself says nothing about the plant's health, so it stays out of the context
            schedules=[
                self._describe_schedule(schedule, current)
                for schedule in schedules
                if schedule.task_type != CareTaskType.PHOTO
            ],
            current_photo_path=current.local_path,
            previous_photo_path=previous.local_path if previous else None,
            days_since_previous_photo=self._days_between(previous, current) if previous else None,
        )

    def _describe_schedule(self, schedule: CareSchedule, current: PlantPhoto) -> PhotoReviewSchedule:
        days_since_last_performed = None
        if schedule.last_performed_at is not None:
            days_since_last_performed = (
                self.household_calendar.local_date(current.taken_at)
                - self.household_calendar.local_date(schedule.last_performed_at)
            ).days
        return PhotoReviewSchedule(
            task_type=CareTaskType(schedule.task_type),
            interval_days=schedule.interval_days,
            days_since_last_performed=days_since_last_performed,
        )

    def _days_between(self, previous: PlantPhoto, current: PlantPhoto) -> int:
        return (
            self.household_calendar.local_date(current.taken_at) - self.household_calendar.local_date(previous.taken_at)
        ).days
