from src.common.constants import CareTaskType
from src.common.exceptions import AlreadyExistsError, DoesNotExistError
from src.modules.plant_care.commands import ArchivePlantCommand, RestorePlantCommand
from src.modules.plant_care.use_cases.archive_plant import ArchivePlantUseCase
from src.modules.plant_care.use_cases.list_plants import ListPlantsUseCase
from src.modules.plant_care.use_cases.restore_plant import RestorePlantUseCase
from src.tests.integration.base import BaseIntegrationTestCase


class RestorePlantTestCase(BaseIntegrationTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.plant_id = await self.seed_plant(name="Кактус")

    async def archive(self) -> None:
        await ArchivePlantUseCase(uow=self.uow)(ArchivePlantCommand(plant_id=self.plant_id))

    async def restore(self, plant_id: int | None = None) -> str:
        return await RestorePlantUseCase(uow=self.uow)(RestorePlantCommand(plant_id=plant_id or self.plant_id))

    async def test_restore_plant_brings_it_back_to_the_list(self):
        await self.archive()

        plant_name = await self.restore()

        self.assertEqual(plant_name, "Кактус")
        plants = await ListPlantsUseCase(uow=self.uow, household_calendar=self.household_calendar)()
        self.assertEqual([plant.name for plant in plants], ["Кактус"])

    async def test_restore_plant_keeps_its_schedules_and_history(self):
        await self.seed_care_schedule(
            plant_id=self.plant_id, task_type=CareTaskType.WATERING, interval_days=4, next_due_on=self.today
        )
        await self.seed_care_event(plant_id=self.plant_id, task_type=CareTaskType.WATERING)
        await self.archive()

        await self.restore()

        schedule = await self.retrieve_care_schedule(self.plant_id, CareTaskType.WATERING)
        self.assertEqual(schedule.interval_days, 4)
        self.assertEqual(len(await self.list_care_events(self.plant_id)), 1)

    async def test_restore_plant_that_was_never_archived_changes_nothing(self):
        plant_name = await self.restore()

        self.assertEqual(plant_name, "Кактус")
        plant = await self.retrieve_plant(self.plant_id)
        self.assertFalse(plant.is_archived)

    async def test_restore_plant_whose_name_was_taken_meanwhile_raises_already_exists(self):
        await self.archive()
        await self.seed_plant(name="Кактус")

        with self.assertRaises(AlreadyExistsError) as context:
            await self.restore()

        self.assertEqual(str(context.exception), "An active plant named 'Кактус' already exists")

    async def test_restore_a_missing_plant_raises_does_not_exist(self):
        with self.assertRaises(DoesNotExistError) as context:
            await self.restore(plant_id=999)

        self.assertEqual(str(context.exception), "Plant 999 not found")
