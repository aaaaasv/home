from src.common.constants import CareTaskType
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.commands import SetCareInstructionsCommand
from src.modules.plant_care.use_cases.set_care_instructions import SetCareInstructionsUseCase
from src.tests.integration.base import BaseIntegrationTestCase


class SetCareInstructionsTestCase(BaseIntegrationTestCase):
    def use_case(self) -> SetCareInstructionsUseCase:
        return SetCareInstructionsUseCase(uow=UnitOfWork(session_factory=self.session_factory))

    async def test_set_care_instructions_writes_them_onto_the_schedule(self):
        plant_id = await self.seed_plant(name="Плющ")
        await self.seed_care_schedule(plant_id=plant_id, task_type=CareTaskType.WATERING)

        await self.use_case()(
            SetCareInstructionsCommand(
                plant_id=plant_id, task_type=CareTaskType.WATERING, instructions="Рясно, але рідко."
            )
        )

        schedule = await self.retrieve_care_schedule(plant_id, CareTaskType.WATERING)
        self.assertEqual(schedule.instructions, "Рясно, але рідко.")

    async def test_set_care_instructions_can_clear_them(self):
        plant_id = await self.seed_plant(name="Плющ")
        await self.seed_care_schedule(plant_id=plant_id, task_type=CareTaskType.WATERING, instructions="старе")

        await self.use_case()(
            SetCareInstructionsCommand(plant_id=plant_id, task_type=CareTaskType.WATERING, instructions=None)
        )

        schedule = await self.retrieve_care_schedule(plant_id, CareTaskType.WATERING)
        self.assertIsNone(schedule.instructions)
