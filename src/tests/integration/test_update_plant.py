from src.common.exceptions import AlreadyExistsError, DoesNotExistError
from src.modules.plant_care.commands import UpdatePlantCommand
from src.modules.plant_care.use_cases.update_plant import UpdatePlantUseCase
from src.tests.integration.base import BaseIntegrationTestCase


class UpdatePlantTestCase(BaseIntegrationTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.plant_id = await self.seed_plant(
            name="Монстера", species="Monstera deliciosa", location="вітальня", notes=None
        )

    def build_use_case(self) -> UpdatePlantUseCase:
        return UpdatePlantUseCase(uow=self.uow)

    async def test_update_plant_name_leaves_the_other_fields_untouched(self):
        command = UpdatePlantCommand(plant_id=self.plant_id, name="Монстера велика")

        await self.build_use_case()(command)

        plant = await self.retrieve_plant(self.plant_id)
        self.assertEqual(plant.name, "Монстера велика")
        self.assertEqual(plant.species, "Monstera deliciosa")
        self.assertEqual(plant.location, "вітальня")

    async def test_update_plant_notes_sets_a_field_that_was_empty(self):
        command = UpdatePlantCommand(plant_id=self.plant_id, notes="боїться протягів")

        await self.build_use_case()(command)

        plant = await self.retrieve_plant(self.plant_id)
        self.assertEqual(plant.notes, "боїться протягів")
        self.assertEqual(plant.name, "Монстера")

    async def test_update_plant_location_to_none_clears_it(self):
        command = UpdatePlantCommand(plant_id=self.plant_id, location=None)

        await self.build_use_case()(command)

        plant = await self.retrieve_plant(self.plant_id)
        self.assertIsNone(plant.location)
        self.assertEqual(plant.species, "Monstera deliciosa")

    async def test_update_plant_name_to_its_own_name_succeeds(self):
        command = UpdatePlantCommand(plant_id=self.plant_id, name="Монстера")

        await self.build_use_case()(command)

        plant = await self.retrieve_plant(self.plant_id)
        self.assertEqual(plant.name, "Монстера")

    async def test_update_plant_name_to_a_taken_name_raises_already_exists(self):
        await self.seed_plant(name="Драцена")
        command = UpdatePlantCommand(plant_id=self.plant_id, name="Драцена")

        with self.assertRaises(AlreadyExistsError) as context:
            await self.build_use_case()(command)

        self.assertEqual(str(context.exception), "Plant 'Драцена' already exists")

    async def test_update_plant_name_to_the_name_of_an_archived_plant_succeeds(self):
        await self.seed_plant(name="Драцена", is_archived=True)
        command = UpdatePlantCommand(plant_id=self.plant_id, name="Драцена")

        await self.build_use_case()(command)

        plant = await self.retrieve_plant(self.plant_id)
        self.assertEqual(plant.name, "Драцена")

    async def test_update_a_missing_plant_raises_does_not_exist(self):
        command = UpdatePlantCommand(plant_id=999, name="Драцена")

        with self.assertRaises(DoesNotExistError) as context:
            await self.build_use_case()(command)

        self.assertEqual(str(context.exception), "Plant 999 not found")
