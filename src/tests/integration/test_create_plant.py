from datetime import date

from src.common.constants import CareTaskType
from src.common.exceptions import AlreadyExistsError
from src.modules.plant_care.commands import CreatePlantCommand, TelegramPhoto
from src.modules.plant_care.use_cases.create_plant import CreatePlantUseCase
from src.tests.factories import OWNER, build_plant_payload
from src.tests.fakes import RecordingPhotoStorage
from src.tests.integration.base import BaseIntegrationTestCase


class CreatePlantTestCase(BaseIntegrationTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.photo_storage = RecordingPhotoStorage()

    def build_use_case(self) -> CreatePlantUseCase:
        return CreatePlantUseCase(
            uow=self.uow,
            actor=OWNER,
            household_calendar=self.household_calendar,
            photo_storage=self.photo_storage,
        )

    async def test_create_plant_watered_today_schedules_next_watering_after_the_interval(self):
        command = CreatePlantCommand(
            name="Монстера",
            species="Monstera deliciosa",
            location="вітальня",
            watering_interval_days=5,
            last_watered_on=self.today,
        )

        card = await self.build_use_case()(command)

        self.assertEqual(card.name, "Монстера")
        self.assertEqual(card.species, "Monstera deliciosa")
        self.assertEqual(card.location, "вітальня")
        self.assertEqual(len(card.schedules), 1)
        self.assertEqual(card.schedules[0].task_type, CareTaskType.WATERING)
        self.assertEqual(card.schedules[0].interval_days, 5)
        self.assertEqual(card.schedules[0].next_due_on, date(2026, 7, 17))
        self.assertEqual(card.schedules[0].days_until_due, 5)

    async def test_create_plant_watered_yesterday_schedules_next_watering_from_that_day(self):
        command = CreatePlantCommand(
            name="Фікус",
            watering_interval_days=7,
            last_watered_on=date(2026, 7, 11),
        )

        card = await self.build_use_case()(command)

        self.assertEqual(card.schedules[0].next_due_on, date(2026, 7, 18))
        self.assertEqual(card.schedules[0].days_until_due, 6)

    async def test_create_plant_with_unknown_last_watering_is_due_today(self):
        command = CreatePlantCommand(name="Фікус", watering_interval_days=7, last_watered_on=None)

        card = await self.build_use_case()(command)

        self.assertEqual(card.schedules[0].next_due_on, self.today)
        self.assertEqual(card.schedules[0].days_until_due, 0)
        self.assertTrue(card.schedules[0].is_due)
        self.assertEqual(card.recent_events, [])

    async def test_create_plant_watered_today_records_the_initial_care_event(self):
        command = CreatePlantCommand(name="Монстера", watering_interval_days=5, last_watered_on=self.today)

        card = await self.build_use_case()(command)

        events = await self.list_care_events(card.id)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].task_type, CareTaskType.WATERING)
        self.assertEqual(events[0].performed_by_display_name, "Богдан")
        self.assertEqual(self.household_calendar.local_date(events[0].performed_at), self.today)

    async def test_create_plant_with_photo_stores_a_local_copy(self):
        command = CreatePlantCommand(
            name="Монстера",
            watering_interval_days=5,
            photo=TelegramPhoto(file_id="file-abc", file_unique_id="unique-abc", caption="перший день"),
        )

        card = await self.build_use_case()(command)

        self.assertEqual(self.photo_storage.saved_file_ids, ["file-abc"])
        self.assertEqual(card.photo_count, 1)
        self.assertEqual(card.latest_photo.telegram_file_id, "file-abc")
        self.assertEqual(card.latest_photo.caption, "перший день")

    async def test_create_plant_with_duplicate_name_raises_already_exists(self):
        await self.seed_plant(**build_plant_payload(name="Монстера"))
        command = CreatePlantCommand(name="Монстера", watering_interval_days=5)

        with self.assertRaises(AlreadyExistsError) as context:
            await self.build_use_case()(command)

        self.assertEqual(str(context.exception), "Plant 'Монстера' already exists")

    async def test_create_plant_reusing_an_archived_name_succeeds(self):
        await self.seed_plant(**build_plant_payload(name="Монстера", is_archived=True))
        command = CreatePlantCommand(name="Монстера", watering_interval_days=5)

        card = await self.build_use_case()(command)

        self.assertEqual(card.name, "Монстера")
