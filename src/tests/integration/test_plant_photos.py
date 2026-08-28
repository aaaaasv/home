from datetime import timedelta

from src.common.constants import CareTaskType, PlantPhotoFrame
from src.common.exceptions import DoesNotExistError
from src.modules.plant_care.commands import AddPlantPhotoCommand, TelegramPhoto
from src.modules.plant_care.use_cases.add_plant_photo import AddPlantPhotoUseCase
from src.modules.plant_care.use_cases.list_plant_photos import ListPlantPhotosUseCase
from src.tests.factories import OWNER
from src.tests.fakes import RecordingPhotoStorage
from src.tests.integration.base import FROZEN_NOW, BaseIntegrationTestCase


class AddPlantPhotoTestCase(BaseIntegrationTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.photo_storage = RecordingPhotoStorage(local_path="photos/unique-abc.jpg")
        self.plant_id = await self.seed_plant(name="Монстера")

    def build_use_case(self) -> AddPlantPhotoUseCase:
        return AddPlantPhotoUseCase(
            uow=self.uow, actor=OWNER, photo_storage=self.photo_storage, household_calendar=self.household_calendar
        )

    async def test_add_plant_photo_success(self):
        command = AddPlantPhotoCommand(
            plant_id=self.plant_id,
            photo=TelegramPhoto(file_id="file-abc", file_unique_id="unique-abc", caption="новий листок"),
            taken_at=FROZEN_NOW,
        )

        photo = await self.build_use_case()(command)

        self.assertEqual(photo.telegram_file_id, "file-abc")
        self.assertEqual(photo.caption, "новий листок")
        self.assertEqual(photo.taken_at, FROZEN_NOW)
        self.assertEqual(self.photo_storage.saved_file_ids, ["file-abc"])

    async def test_add_plant_photo_without_a_stated_frame_is_stored_as_an_overview(self):
        command = AddPlantPhotoCommand(
            plant_id=self.plant_id,
            photo=TelegramPhoto(file_id="file-abc", file_unique_id="unique-abc", caption=None),
            taken_at=FROZEN_NOW,
        )

        photo = await self.build_use_case()(command)

        self.assertEqual(photo.frame, PlantPhotoFrame.OVERVIEW)

    async def test_add_plant_photo_as_a_close_up_is_stored_as_a_detail(self):
        command = AddPlantPhotoCommand(
            plant_id=self.plant_id,
            photo=TelegramPhoto(file_id="file-leaf", file_unique_id="unique-leaf", caption=None),
            taken_at=FROZEN_NOW,
            frame=PlantPhotoFrame.DETAIL,
        )

        photo = await self.build_use_case()(command)

        self.assertEqual(photo.frame, PlantPhotoFrame.DETAIL)

    async def test_add_plant_photo_with_a_photo_schedule_moves_the_next_one_a_full_interval_away(self):
        await self.seed_care_schedule(
            plant_id=self.plant_id,
            task_type=CareTaskType.PHOTO,
            interval_days=30,
            next_due_on=self.today - timedelta(days=3),
        )
        command = AddPlantPhotoCommand(
            plant_id=self.plant_id,
            photo=TelegramPhoto(file_id="file-abc", file_unique_id="unique-abc"),
            taken_at=FROZEN_NOW,
        )

        await self.build_use_case()(command)

        schedule = await self.retrieve_care_schedule(self.plant_id, CareTaskType.PHOTO)
        self.assertEqual(schedule.next_due_on, self.today + timedelta(days=30))
        self.assertEqual(schedule.last_performed_at, FROZEN_NOW)

    async def test_add_plant_photo_without_a_photo_schedule_leaves_the_other_schedules_untouched(self):
        await self.seed_care_schedule(
            plant_id=self.plant_id,
            task_type=CareTaskType.WATERING,
            interval_days=4,
            next_due_on=self.today,
        )
        command = AddPlantPhotoCommand(
            plant_id=self.plant_id,
            photo=TelegramPhoto(file_id="file-abc", file_unique_id="unique-abc"),
            taken_at=FROZEN_NOW,
        )

        await self.build_use_case()(command)

        schedule = await self.retrieve_care_schedule(self.plant_id, CareTaskType.WATERING)
        self.assertEqual(schedule.next_due_on, self.today)
        self.assertIsNone(schedule.last_performed_at)

    async def test_add_plant_photo_for_a_missing_plant_raises_does_not_exist(self):
        command = AddPlantPhotoCommand(
            plant_id=999,
            photo=TelegramPhoto(file_id="file-abc", file_unique_id="unique-abc"),
            taken_at=FROZEN_NOW,
        )

        with self.assertRaises(DoesNotExistError) as context:
            await self.build_use_case()(command)

        self.assertEqual(str(context.exception), "Plant 999 not found")


class ListPlantPhotosTestCase(BaseIntegrationTestCase):
    async def test_list_plant_photos_returns_the_timeline_oldest_first(self):
        plant_id = await self.seed_plant(name="Монстера")
        await self.seed_plant_photo(
            plant_id=plant_id,
            telegram_file_id="file-new",
            telegram_file_unique_id="unique-2",
            taken_at=FROZEN_NOW,
        )
        await self.seed_plant_photo(
            plant_id=plant_id,
            telegram_file_id="file-old",
            telegram_file_unique_id="unique-1",
            taken_at=FROZEN_NOW - timedelta(days=30),
        )

        photos = await ListPlantPhotosUseCase(uow=self.uow)(plant_id)

        self.assertEqual([photo.telegram_file_id for photo in photos], ["file-old", "file-new"])
