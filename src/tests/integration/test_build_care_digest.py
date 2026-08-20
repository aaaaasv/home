from datetime import date, datetime, timedelta, timezone

from src.common.constants import CareTaskType
from src.modules.plant_care.use_cases.build_care_digest import BuildCareDigestUseCase
from src.tests.integration.base import BaseIntegrationTestCase


class BuildCareDigestTestCase(BaseIntegrationTestCase):
    def build_use_case(self) -> BuildCareDigestUseCase:
        return BuildCareDigestUseCase(uow=self.uow, household_calendar=self.household_calendar)

    async def test_build_care_digest_returns_tasks_due_today(self):
        plant_id = await self.seed_plant(name="Монстера")
        await self.seed_care_schedule(plant_id=plant_id, task_type=CareTaskType.WATERING, next_due_on=self.today)

        digest = await self.build_use_case()()

        self.assertEqual(digest.today, date(2026, 7, 12))
        self.assertEqual(len(digest.tasks), 1)
        self.assertEqual(digest.tasks[0].plant_name, "Монстера")
        self.assertEqual(digest.tasks[0].task_type, CareTaskType.WATERING)
        self.assertEqual(digest.tasks[0].overdue_days, 0)

    async def test_build_care_digest_reports_overdue_days(self):
        plant_id = await self.seed_plant(name="Фікус")
        await self.seed_care_schedule(
            plant_id=plant_id, task_type=CareTaskType.WATERING, next_due_on=self.today - timedelta(days=3)
        )

        digest = await self.build_use_case()()

        self.assertEqual(len(digest.tasks), 1)
        self.assertEqual(digest.tasks[0].plant_name, "Фікус")
        self.assertEqual(digest.tasks[0].overdue_days, 3)

    async def test_build_care_digest_excludes_tasks_due_in_the_future(self):
        plant_id = await self.seed_plant(name="Монстера")
        await self.seed_care_schedule(
            plant_id=plant_id, task_type=CareTaskType.WATERING, next_due_on=self.today + timedelta(days=1)
        )

        digest = await self.build_use_case()()

        self.assertEqual(digest.tasks, [])

    async def test_build_care_digest_excludes_archived_plants(self):
        plant_id = await self.seed_plant(name="Кактус", is_archived=True)
        await self.seed_care_schedule(plant_id=plant_id, task_type=CareTaskType.WATERING, next_due_on=self.today)

        digest = await self.build_use_case()()

        self.assertEqual(digest.tasks, [])

    async def test_build_care_digest_orders_the_most_overdue_task_first(self):
        monstera_id = await self.seed_plant(name="Монстера")
        ficus_id = await self.seed_plant(name="Фікус")
        await self.seed_care_schedule(plant_id=monstera_id, task_type=CareTaskType.WATERING, next_due_on=self.today)
        await self.seed_care_schedule(
            plant_id=ficus_id, task_type=CareTaskType.WATERING, next_due_on=self.today - timedelta(days=4)
        )
        await self.seed_care_schedule(
            plant_id=monstera_id, task_type=CareTaskType.FERTILIZING, next_due_on=self.today - timedelta(days=1)
        )

        digest = await self.build_use_case()()

        self.assertEqual(
            [(task.plant_name, task.task_type, task.overdue_days) for task in digest.tasks],
            [
                ("Фікус", CareTaskType.WATERING, 4),
                ("Монстера", CareTaskType.FERTILIZING, 1),
                ("Монстера", CareTaskType.WATERING, 0),
            ],
        )

    async def test_build_care_digest_carries_the_latest_photo_of_each_plant(self):
        plant_id = await self.seed_plant(name="Монстера")
        await self.seed_care_schedule(plant_id=plant_id, task_type=CareTaskType.WATERING, next_due_on=self.today)
        await self.seed_plant_photo(
            plant_id=plant_id,
            telegram_file_id="old",
            telegram_file_unique_id="unique-old",
            taken_at=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
        )
        await self.seed_plant_photo(
            plant_id=plant_id,
            telegram_file_id="latest",
            telegram_file_unique_id="unique-latest",
            taken_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        )

        digest = await self.build_use_case()()

        self.assertEqual(digest.tasks[0].photo_file_id, "latest")

    async def test_build_care_digest_leaves_the_photo_absent_when_the_plant_has_none(self):
        plant_id = await self.seed_plant(name="Фікус")
        await self.seed_care_schedule(plant_id=plant_id, task_type=CareTaskType.WATERING, next_due_on=self.today)

        digest = await self.build_use_case()()

        self.assertIsNone(digest.tasks[0].photo_file_id)

    async def test_build_care_digest_carries_the_task_instructions(self):
        plant_id = await self.seed_plant(name="Плющ")
        await self.seed_care_schedule(
            plant_id=plant_id,
            task_type=CareTaskType.WATERING,
            next_due_on=self.today,
            instructions="Поливайте рясно, але рідко.",
        )

        digest = await self.build_use_case()()

        self.assertEqual(digest.tasks[0].instructions, "Поливайте рясно, але рідко.")
