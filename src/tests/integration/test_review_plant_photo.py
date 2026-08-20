from datetime import timedelta

from src.common.constants import CareTaskType, PlantPhotoReviewStatus
from src.modules.plant_care.domain import PlantPhotoReview
from src.modules.plant_care.use_cases.review_plant_photo import ReviewPlantPhotoUseCase
from src.tests.fakes import RecordingPhotoAnalyst
from src.tests.integration.base import FROZEN_NOW, BaseIntegrationTestCase

HEALTHY_REVIEW = PlantPhotoReview(
    status=PlantPhotoReviewStatus.OK,
    summary="Виглядає здоровою.",
    change=None,
    action=None,
)


class ReviewPlantPhotoTestCase(BaseIntegrationTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.photo_analyst = RecordingPhotoAnalyst(review=HEALTHY_REVIEW)
        self.plant_id = await self.seed_plant(
            name="Пеперомія",
            species="Peperomia obtusifolia",
            location="кухня",
            ideal_temperature_min_celsius=18.0,
            ideal_temperature_max_celsius=26.0,
            ideal_humidity_min_percent=40.0,
            ideal_humidity_max_percent=60.0,
        )

    def build_use_case(self) -> ReviewPlantPhotoUseCase:
        return ReviewPlantPhotoUseCase(
            uow=self.uow, household_calendar=self.household_calendar, photo_analyst=self.photo_analyst
        )

    async def test_review_plant_photo_passes_the_previous_photo_and_the_gap_between_them(self):
        await self.seed_plant_photo(
            plant_id=self.plant_id,
            telegram_file_unique_id="unique-old",
            local_path="photos/old.jpg",
            taken_at=FROZEN_NOW - timedelta(days=31),
        )
        await self.seed_plant_photo(
            plant_id=self.plant_id,
            telegram_file_unique_id="unique-new",
            local_path="photos/new.jpg",
            taken_at=FROZEN_NOW,
        )

        review = await self.build_use_case()(self.plant_id)

        self.assertEqual(review, HEALTHY_REVIEW)
        context = self.photo_analyst.reviewed_contexts[0]
        self.assertEqual(context.current_photo_path, "photos/new.jpg")
        self.assertEqual(context.previous_photo_path, "photos/old.jpg")
        self.assertEqual(context.days_since_previous_photo, 31)

    async def test_review_plant_photo_passes_the_plant_profile_and_the_room_climate(self):
        await self.seed_room_climate_readings(
            humidity_percent=31.0,
            temperature_celsius=27.0,
            since=FROZEN_NOW - timedelta(hours=1),
            until=FROZEN_NOW,
        )
        await self.seed_plant_photo(plant_id=self.plant_id, local_path="photos/new.jpg", taken_at=FROZEN_NOW)

        await self.build_use_case()(self.plant_id)

        context = self.photo_analyst.reviewed_contexts[0]
        self.assertEqual(context.plant_name, "Пеперомія")
        self.assertEqual(context.species, "Peperomia obtusifolia")
        self.assertEqual(context.location, "кухня")
        self.assertEqual(context.ideal_temperature_min_celsius, 18.0)
        self.assertEqual(context.ideal_temperature_max_celsius, 26.0)
        self.assertEqual(context.ideal_humidity_min_percent, 40.0)
        self.assertEqual(context.ideal_humidity_max_percent, 60.0)
        self.assertEqual(context.room_temperature_celsius, 27.0)
        self.assertEqual(context.room_humidity_percent, 31.0)

    async def test_review_plant_photo_passes_the_care_schedules_without_the_photo_one(self):
        await self.seed_care_schedule(
            plant_id=self.plant_id,
            task_type=CareTaskType.WATERING,
            interval_days=3,
            last_performed_at=FROZEN_NOW - timedelta(days=2),
        )
        await self.seed_care_schedule(plant_id=self.plant_id, task_type=CareTaskType.PHOTO, interval_days=30)
        await self.seed_plant_photo(plant_id=self.plant_id, local_path="photos/new.jpg", taken_at=FROZEN_NOW)

        await self.build_use_case()(self.plant_id)

        context = self.photo_analyst.reviewed_contexts[0]
        self.assertEqual([schedule.task_type for schedule in context.schedules], [CareTaskType.WATERING])
        self.assertEqual(context.schedules[0].interval_days, 3)
        self.assertEqual(context.schedules[0].days_since_last_performed, 2)

    async def test_review_plant_photo_with_the_only_photo_has_nothing_to_compare_with(self):
        await self.seed_plant_photo(plant_id=self.plant_id, local_path="photos/new.jpg", taken_at=FROZEN_NOW)

        await self.build_use_case()(self.plant_id)

        context = self.photo_analyst.reviewed_contexts[0]
        self.assertIsNone(context.previous_photo_path)
        self.assertIsNone(context.days_since_previous_photo)

    async def test_review_plant_photo_skips_a_previous_photo_that_was_never_stored_locally(self):
        await self.seed_plant_photo(
            plant_id=self.plant_id,
            telegram_file_unique_id="unique-oldest",
            local_path="photos/oldest.jpg",
            taken_at=FROZEN_NOW - timedelta(days=60),
        )
        await self.seed_plant_photo(
            plant_id=self.plant_id,
            telegram_file_unique_id="unique-failed",
            local_path=None,
            taken_at=FROZEN_NOW - timedelta(days=30),
        )
        await self.seed_plant_photo(
            plant_id=self.plant_id,
            telegram_file_unique_id="unique-new",
            local_path="photos/new.jpg",
            taken_at=FROZEN_NOW,
        )

        await self.build_use_case()(self.plant_id)

        context = self.photo_analyst.reviewed_contexts[0]
        self.assertEqual(context.previous_photo_path, "photos/oldest.jpg")
        self.assertEqual(context.days_since_previous_photo, 60)

    async def test_review_plant_photo_without_a_local_copy_is_not_sent_for_review(self):
        await self.seed_plant_photo(plant_id=self.plant_id, local_path=None, taken_at=FROZEN_NOW)

        review = await self.build_use_case()(self.plant_id)

        self.assertIsNone(review)
        self.assertEqual(self.photo_analyst.reviewed_contexts, [])
