from datetime import timedelta

from src.common.constants import CareTaskType
from src.common.exceptions import ConflictError, DoesNotExistError
from src.modules.plant_care.commands import RecordCareEventCommand, UndoCareEventCommand
from src.modules.plant_care.use_cases.record_care_event import RecordCareEventUseCase
from src.modules.plant_care.use_cases.undo_care_event import UndoCareEventUseCase
from src.tests.factories import OWNER
from src.tests.integration.base import FROZEN_NOW, BaseIntegrationTestCase

GUARD_HOURS = 12


class UndoCareEventTestCase(BaseIntegrationTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.plant_id = await self.seed_plant(name="Кактус")

    async def record(self, performed_at=FROZEN_NOW):
        return await RecordCareEventUseCase(
            uow=self.uow, actor=OWNER, household_calendar=self.household_calendar, recent_care_guard_hours=GUARD_HOURS
        )(
            RecordCareEventCommand(
                plant_id=self.plant_id,
                task_type=CareTaskType.WATERING,
                performed_at=performed_at,
                force=True,
            )
        )

    async def undo(self):
        return await UndoCareEventUseCase(uow=self.uow, household_calendar=self.household_calendar)(
            UndoCareEventCommand(plant_id=self.plant_id, task_type=CareTaskType.WATERING)
        )

    async def test_undo_care_event_puts_the_schedule_back_on_the_date_the_record_replaced(self):
        overdue_on = self.today - timedelta(days=4)
        await self.seed_care_schedule(
            plant_id=self.plant_id, task_type=CareTaskType.WATERING, interval_days=7, next_due_on=overdue_on
        )
        await self.record()

        task = await self.undo()

        schedule = await self.retrieve_care_schedule(self.plant_id, CareTaskType.WATERING)
        self.assertEqual(schedule.next_due_on, overdue_on)
        self.assertEqual(task.overdue_days, 4)

    async def test_undo_care_event_removes_the_record_from_the_history(self):
        await self.seed_care_schedule(
            plant_id=self.plant_id, task_type=CareTaskType.WATERING, interval_days=7, next_due_on=self.today
        )
        await self.record()

        await self.undo()

        self.assertEqual(await self.list_care_events(self.plant_id), [])

    async def test_undo_care_event_restores_the_last_care_to_the_record_before_it(self):
        await self.seed_care_schedule(
            plant_id=self.plant_id, task_type=CareTaskType.WATERING, interval_days=7, next_due_on=self.today
        )
        earlier = FROZEN_NOW - timedelta(days=7)
        await self.record(performed_at=earlier)
        await self.record()

        await self.undo()

        schedule = await self.retrieve_care_schedule(self.plant_id, CareTaskType.WATERING)
        self.assertEqual(schedule.last_performed_at, earlier)
        self.assertEqual([event.performed_at for event in await self.list_care_events(self.plant_id)], [earlier])

    async def test_undo_care_event_on_the_only_record_leaves_the_plant_never_cared_for(self):
        await self.seed_care_schedule(
            plant_id=self.plant_id, task_type=CareTaskType.WATERING, interval_days=7, next_due_on=self.today
        )
        await self.record()

        await self.undo()

        schedule = await self.retrieve_care_schedule(self.plant_id, CareTaskType.WATERING)
        self.assertIsNone(schedule.last_performed_at)

    async def test_undo_care_event_returns_the_task_ready_to_be_recorded_again(self):
        await self.seed_care_schedule(
            plant_id=self.plant_id, task_type=CareTaskType.WATERING, interval_days=7, next_due_on=self.today
        )
        await self.seed_plant_photo(plant_id=self.plant_id, telegram_file_id="file-latest", taken_at=FROZEN_NOW)
        await self.record()

        task = await self.undo()

        self.assertEqual(task.plant_name, "Кактус")
        self.assertEqual(task.task_type, CareTaskType.WATERING)
        self.assertEqual(task.interval_days, 7)
        self.assertEqual(task.overdue_days, 0)
        self.assertEqual(task.photo_file_id, "file-latest")

    async def test_undo_care_event_with_nothing_recorded_raises_does_not_exist(self):
        await self.seed_care_schedule(
            plant_id=self.plant_id, task_type=CareTaskType.WATERING, interval_days=7, next_due_on=self.today
        )

        with self.assertRaises(DoesNotExistError) as context:
            await self.undo()

        self.assertEqual(str(context.exception), "Plant 'Кактус' has no watering to undo")

    async def test_undo_care_event_after_the_schedule_was_removed_raises_does_not_exist(self):
        await self.seed_care_schedule(
            plant_id=self.plant_id, task_type=CareTaskType.WATERING, interval_days=7, next_due_on=self.today
        )
        await self.record()
        await self.remove_care_schedule(self.plant_id, CareTaskType.WATERING)

        with self.assertRaises(DoesNotExistError) as context:
            await self.undo()

        self.assertEqual(str(context.exception), "Plant 'Кактус' no longer has a watering schedule")

    async def test_undo_care_event_recorded_before_the_previous_due_date_was_kept_raises_conflict(self):
        await self.seed_care_schedule(
            plant_id=self.plant_id, task_type=CareTaskType.WATERING, interval_days=7, next_due_on=self.today
        )
        await self.record()
        await self.forget_previous_due_date(self.plant_id, CareTaskType.WATERING)

        with self.assertRaises(ConflictError) as context:
            await self.undo()

        self.assertEqual(str(context.exception), "This watering record is too old to undo")
