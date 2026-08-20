from datetime import date, timedelta

from pydantic import ValidationError as PydanticValidationError

from src.common.constants import CareTaskType
from src.common.exceptions import DoesNotExistError, ValidationError
from src.modules.plant_care.commands import RemoveCareScheduleCommand, SetCareScheduleCommand
from src.modules.plant_care.use_cases.remove_care_schedule import RemoveCareScheduleUseCase
from src.modules.plant_care.use_cases.set_care_schedule import SetCareScheduleUseCase
from src.tests.integration.base import FROZEN_NOW, BaseIntegrationTestCase


class SetCareScheduleTestCase(BaseIntegrationTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.plant_id = await self.seed_plant(name="Монстера")
        await self.seed_care_schedule(
            plant_id=self.plant_id, task_type=CareTaskType.WATERING, interval_days=5, next_due_on=self.today
        )

    def build_use_case(self) -> SetCareScheduleUseCase:
        return SetCareScheduleUseCase(uow=self.uow, household_calendar=self.household_calendar)

    async def test_set_care_schedule_for_a_new_task_makes_it_due_today(self):
        command = SetCareScheduleCommand(plant_id=self.plant_id, task_type=CareTaskType.FERTILIZING, interval_days=30)

        schedule = await self.build_use_case()(command)

        self.assertEqual(schedule.task_type, CareTaskType.FERTILIZING)
        self.assertEqual(schedule.interval_days, 30)
        self.assertEqual(schedule.next_due_on, self.today)
        self.assertIsNone(schedule.last_performed_at)

    async def test_set_care_schedule_for_an_existing_task_reschedules_from_the_last_care(self):
        watered_at = FROZEN_NOW - timedelta(days=1)
        await self.seed_care_schedule(
            plant_id=self.plant_id,
            task_type=CareTaskType.ROTATING,
            interval_days=2,
            next_due_on=self.today + timedelta(days=1),
            last_performed_at=watered_at,
        )
        command = SetCareScheduleCommand(plant_id=self.plant_id, task_type=CareTaskType.ROTATING, interval_days=10)

        schedule = await self.build_use_case()(command)

        self.assertEqual(schedule.interval_days, 10)
        self.assertEqual(schedule.next_due_on, date(2026, 7, 21))

    async def test_set_care_schedule_for_a_never_performed_task_makes_it_due_today(self):
        await self.seed_care_schedule(
            plant_id=self.plant_id,
            task_type=CareTaskType.ROTATING,
            interval_days=2,
            next_due_on=self.today + timedelta(days=1),
        )
        command = SetCareScheduleCommand(plant_id=self.plant_id, task_type=CareTaskType.ROTATING, interval_days=10)

        schedule = await self.build_use_case()(command)

        self.assertEqual(schedule.next_due_on, self.today)

    async def test_set_care_schedule_for_repotting_every_three_years_reschedules_from_the_last_care(self):
        repotted_at = FROZEN_NOW - timedelta(days=5)
        await self.seed_care_schedule(
            plant_id=self.plant_id,
            task_type=CareTaskType.REPOTTING,
            interval_days=365,
            next_due_on=self.today + timedelta(days=360),
            last_performed_at=repotted_at,
        )
        command = SetCareScheduleCommand(plant_id=self.plant_id, task_type=CareTaskType.REPOTTING, interval_days=1095)

        schedule = await self.build_use_case()(command)

        self.assertEqual(schedule.interval_days, 1095)
        self.assertEqual(schedule.next_due_on, date(2029, 7, 6))

    async def test_set_care_schedule_above_the_maximum_interval_is_rejected_by_the_command(self):
        with self.assertRaises(PydanticValidationError) as context:
            SetCareScheduleCommand(plant_id=self.plant_id, task_type=CareTaskType.REPOTTING, interval_days=1096)

        self.assertEqual(
            [(error["loc"], error["type"]) for error in context.exception.errors()],
            [(("interval_days",), "less_than_equal")],
        )

    async def test_set_care_schedule_for_a_missing_plant_raises_does_not_exist(self):
        command = SetCareScheduleCommand(plant_id=999, task_type=CareTaskType.FERTILIZING, interval_days=30)

        with self.assertRaises(DoesNotExistError) as context:
            await self.build_use_case()(command)

        self.assertEqual(str(context.exception), "Plant 999 not found")


class RemoveCareScheduleTestCase(BaseIntegrationTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.plant_id = await self.seed_plant(name="Монстера")
        await self.seed_care_schedule(plant_id=self.plant_id, task_type=CareTaskType.WATERING)
        await self.seed_care_schedule(plant_id=self.plant_id, task_type=CareTaskType.FERTILIZING)

    def build_use_case(self) -> RemoveCareScheduleUseCase:
        return RemoveCareScheduleUseCase(uow=self.uow)

    async def test_remove_care_schedule_success(self):
        command = RemoveCareScheduleCommand(plant_id=self.plant_id, task_type=CareTaskType.FERTILIZING)

        await self.build_use_case()(command)

        self.assertIsNone(await self.retrieve_care_schedule(self.plant_id, CareTaskType.FERTILIZING))
        self.assertIsNotNone(await self.retrieve_care_schedule(self.plant_id, CareTaskType.WATERING))

    async def test_remove_watering_schedule_raises_validation_error(self):
        command = RemoveCareScheduleCommand(plant_id=self.plant_id, task_type=CareTaskType.WATERING)

        with self.assertRaises(ValidationError) as context:
            await self.build_use_case()(command)

        self.assertEqual(str(context.exception), "Watering schedule cannot be removed")

    async def test_remove_an_unscheduled_task_raises_does_not_exist(self):
        command = RemoveCareScheduleCommand(plant_id=self.plant_id, task_type=CareTaskType.REPOTTING)

        with self.assertRaises(DoesNotExistError) as context:
            await self.build_use_case()(command)

        self.assertEqual(str(context.exception), f"Plant {self.plant_id} has no repotting schedule")
