from statistics import mean

from src.common.constants import CareTaskType, PlantPhotoFrame
from src.common.exceptions import DoesNotExistError
from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.models import CareSchedule, Plant, PlantPhoto, RoomClimateDay, RoomClimateReading
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.domain import (
    ClimateInterval,
    PhotoReviewSchedule,
    PlantPhotoReview,
    PlantPhotoReviewContext,
)
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
            current, previous = self._comparable_pair(photos)
            climate_days = []
            if current is not None and previous is not None:
                climate_days = await uow.room_climate_days.list_between(
                    self.household_calendar.local_date(previous.taken_at),
                    self.household_calendar.local_date(current.taken_at),
                )

        context = self._build_context(plant, photos, schedules, room_climate, climate_days)
        if context is None:
            return None

        return await self.photo_analyst.review_photo(context)

    def _build_context(
        self,
        plant: Plant,
        photos: list[PlantPhoto],
        schedules: list[CareSchedule],
        room_climate: RoomClimateReading | None,
        climate_days: list[RoomClimateDay],
    ) -> PlantPhotoReviewContext | None:
        current, previous = self._comparable_pair(photos)
        if current is None:
            return None
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
            current_photo_taken_on=self.household_calendar.local_date(current.taken_at),
            previous_photo_path=previous.local_path if previous else None,
            previous_photo_taken_on=self.household_calendar.local_date(previous.taken_at) if previous else None,
            days_since_previous_photo=self._days_between(previous, current) if previous else None,
            climate_between_photos=self._summarise_climate(climate_days, plant.ideal_humidity_min_percent),
        )

    def _comparable_pair(self, photos: list[PlantPhoto]) -> tuple[PlantPhoto | None, PlantPhoto | None]:
        """
        The newest general frame and the one before it.

        only general frames are comparable: judging a close-up of one leaf against last month's whole-plant shot
        would report changes that are only a change of distance. a photo whose download failed has no local copy
        and there is nothing to send without one.
        """
        overviews = [photo for photo in photos if photo.frame == PlantPhotoFrame.OVERVIEW.value]
        if not overviews or overviews[-1].local_path is None:
            return None, None
        current = overviews[-1]
        previous = next((photo for photo in reversed(overviews[:-1]) if photo.local_path is not None), None)
        return current, previous

    def _summarise_climate(
        self, climate_days: list[RoomClimateDay], ideal_humidity_min_percent: float | None
    ) -> ClimateInterval | None:
        """The span and the middle of the air between two photos, plus how much of it the plant disliked."""
        if not climate_days:
            return None
        below = None
        if ideal_humidity_min_percent is not None:
            below = sum(1 for day in climate_days if day.average_humidity_percent < ideal_humidity_min_percent)
        return ClimateInterval(
            days_recorded=len(climate_days),
            minimum_temperature_celsius=min(day.minimum_temperature_celsius for day in climate_days),
            maximum_temperature_celsius=max(day.maximum_temperature_celsius for day in climate_days),
            average_temperature_celsius=mean(day.average_temperature_celsius for day in climate_days),
            minimum_humidity_percent=min(day.minimum_humidity_percent for day in climate_days),
            maximum_humidity_percent=max(day.maximum_humidity_percent for day in climate_days),
            average_humidity_percent=mean(day.average_humidity_percent for day in climate_days),
            days_below_ideal_humidity=below,
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
