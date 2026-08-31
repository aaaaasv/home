from datetime import timedelta

from src.common.constants import CareTaskType
from src.common.exceptions import DoesNotExistError
from src.modules.plant_care.commands import ArchivePlantCommand
from src.modules.plant_care.use_cases.archive_plant import ArchivePlantUseCase
from src.modules.plant_care.use_cases.list_plants import ListPlantsUseCase
from src.modules.plant_care.use_cases.retrieve_plant_card import RetrievePlantCardUseCase
from src.tests.factories import PARTNER
from src.tests.integration.base import FROZEN_NOW, BaseIntegrationTestCase


class ListPlantsTestCase(BaseIntegrationTestCase):
    def build_use_case(self) -> ListPlantsUseCase:
        return ListPlantsUseCase(uow=self.uow, household_calendar=self.household_calendar)

    async def test_list_plants_with_no_plants_returns_empty_list(self):
        plants = await self.build_use_case()()

        self.assertEqual(plants, [])

    async def test_list_plants_returns_active_plants_sorted_by_name_with_schedules(self):
        monstera_id = await self.seed_plant(name="Монстера", location="вітальня")
        ficus_id = await self.seed_plant(name="Фікус", location=None)
        await self.seed_care_schedule(
            plant_id=monstera_id, task_type=CareTaskType.WATERING, interval_days=5, next_due_on=self.today
        )
        await self.seed_care_schedule(
            plant_id=ficus_id,
            task_type=CareTaskType.WATERING,
            interval_days=7,
            next_due_on=self.today + timedelta(days=3),
        )

        plants = await self.build_use_case()()

        self.assertEqual([plant.name for plant in plants], ["Монстера", "Фікус"])
        self.assertEqual(plants[0].location, "вітальня")
        self.assertEqual(plants[0].schedules[0].days_until_due, 0)
        self.assertTrue(plants[0].schedules[0].is_due)
        self.assertEqual(plants[1].schedules[0].days_until_due, 3)
        self.assertFalse(plants[1].schedules[0].is_due)

    async def test_list_plants_excludes_archived_plants(self):
        await self.seed_plant(name="Монстера")
        await self.seed_plant(name="Кактус", is_archived=True)

        plants = await self.build_use_case()()

        self.assertEqual([plant.name for plant in plants], ["Монстера"])

    async def test_list_plants_reports_the_most_urgent_schedule_per_plant(self):
        plant_id = await self.seed_plant(name="Монстера")
        await self.seed_care_schedule(
            plant_id=plant_id,
            task_type=CareTaskType.WATERING,
            next_due_on=self.today + timedelta(days=4),
        )
        await self.seed_care_schedule(
            plant_id=plant_id,
            task_type=CareTaskType.FERTILIZING,
            next_due_on=self.today - timedelta(days=2),
        )

        plants = await self.build_use_case()()

        self.assertEqual(plants[0].most_urgent_schedule.task_type, CareTaskType.FERTILIZING)
        self.assertEqual(plants[0].most_urgent_schedule.overdue_days, 2)


class RetrievePlantCardTestCase(BaseIntegrationTestCase):
    def build_use_case(self) -> RetrievePlantCardUseCase:
        return RetrievePlantCardUseCase(uow=self.uow, household_calendar=self.household_calendar)

    async def test_retrieve_plant_card_returns_schedules_history_and_photos(self):
        plant_id = await self.seed_plant(name="Монстера", species="Monstera deliciosa")
        await self.seed_care_schedule(plant_id=plant_id, task_type=CareTaskType.WATERING, interval_days=5)
        await self.seed_care_event(
            plant_id=plant_id,
            task_type=CareTaskType.WATERING,
            performed_at=FROZEN_NOW - timedelta(days=1),
            performed_by=PARTNER,
        )
        await self.seed_plant_photo(plant_id=plant_id, telegram_file_id="file-old", taken_at=FROZEN_NOW)
        await self.seed_plant_photo(
            plant_id=plant_id, telegram_file_id="file-new", telegram_file_unique_id="unique-2", taken_at=FROZEN_NOW
        )

        card = await self.build_use_case()(plant_id)

        self.assertEqual(card.name, "Монстера")
        self.assertEqual(card.species, "Monstera deliciosa")
        self.assertEqual(len(card.schedules), 1)
        self.assertEqual(len(card.recent_events), 1)
        self.assertEqual(card.recent_events[0].performed_by_display_name, "Марта")
        self.assertEqual(card.photo_count, 2)
        self.assertEqual(card.latest_photo.telegram_file_id, "file-new")

    async def test_retrieve_plant_card_for_a_missing_plant_raises_does_not_exist(self):
        with self.assertRaises(DoesNotExistError) as context:
            await self.build_use_case()(999)

        self.assertEqual(str(context.exception), "Plant 999 not found")


class ArchivePlantTestCase(BaseIntegrationTestCase):
    async def test_archive_plant_removes_it_from_the_list(self):
        plant_id = await self.seed_plant(name="Монстера")

        plant_name = await ArchivePlantUseCase(uow=self.uow, household_calendar=self.household_calendar)(
            ArchivePlantCommand(plant_id=plant_id)
        )

        self.assertEqual(plant_name, "Монстера")
        self.assertEqual(await ListPlantsUseCase(uow=self.uow, household_calendar=self.household_calendar)(), [])

    async def test_archive_plant_for_a_missing_plant_raises_does_not_exist(self):
        with self.assertRaises(DoesNotExistError) as context:
            await ArchivePlantUseCase(uow=self.uow, household_calendar=self.household_calendar)(
                ArchivePlantCommand(plant_id=999)
            )

        self.assertEqual(str(context.exception), "Plant 999 not found")
