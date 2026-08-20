from datetime import timedelta

from src.common.constants import CareTaskType
from src.common.exceptions import DoesNotExistError
from src.modules.plant_care.commands import PostponeCareTaskCommand
from src.modules.plant_care.use_cases.postpone_care_task import PostponeCareTaskUseCase
from src.tests.integration.base import FROZEN_NOW, BaseIntegrationTestCase


class PostponeCareTaskTestCase(BaseIntegrationTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.plant_id = await self.seed_plant(name="Кактус")

    async def postpone(self, task_type: CareTaskType = CareTaskType.WATERING):
        return await PostponeCareTaskUseCase(uow=self.uow, household_calendar=self.household_calendar)(
            PostponeCareTaskCommand(plant_id=self.plant_id, task_type=task_type, postponed_at=FROZEN_NOW)
        )

    async def test_postpone_care_task_moves_it_a_third_of_the_interval_away(self):
        await self.seed_care_schedule(
            plant_id=self.plant_id, task_type=CareTaskType.WATERING, interval_days=7, next_due_on=self.today
        )

        postponed = await self.postpone()

        self.assertEqual(postponed.next_due_on, self.today + timedelta(days=2))
        schedule = await self.retrieve_care_schedule(self.plant_id, CareTaskType.WATERING)
        self.assertEqual(schedule.next_due_on, self.today + timedelta(days=2))

    async def test_postpone_care_task_with_a_very_long_interval_is_capped_at_two_weeks(self):
        await self.seed_care_schedule(
            plant_id=self.plant_id, task_type=CareTaskType.REPOTTING, interval_days=1095, next_due_on=self.today
        )

        postponed = await self.postpone(CareTaskType.REPOTTING)

        self.assertEqual(postponed.next_due_on, self.today + timedelta(days=14))

    async def test_postpone_a_skippable_fertilizing_task_moves_it_a_full_interval_away(self):
        await self.seed_care_schedule(
            plant_id=self.plant_id, task_type=CareTaskType.FERTILIZING, interval_days=30, next_due_on=self.today
        )

        postponed = await self.postpone(CareTaskType.FERTILIZING)

        self.assertEqual(postponed.next_due_on, self.today + timedelta(days=30))
        schedule = await self.retrieve_care_schedule(self.plant_id, CareTaskType.FERTILIZING)
        self.assertEqual(schedule.next_due_on, self.today + timedelta(days=30))

    async def test_postpone_a_skippable_photo_task_moves_it_a_full_interval_away(self):
        await self.seed_care_schedule(
            plant_id=self.plant_id, task_type=CareTaskType.PHOTO, interval_days=30, next_due_on=self.today
        )

        postponed = await self.postpone(CareTaskType.PHOTO)

        self.assertEqual(postponed.next_due_on, self.today + timedelta(days=30))

    async def test_postpone_care_task_with_a_very_short_interval_still_moves_a_full_day(self):
        await self.seed_care_schedule(
            plant_id=self.plant_id, task_type=CareTaskType.WATERING, interval_days=2, next_due_on=self.today
        )

        postponed = await self.postpone()

        self.assertEqual(postponed.next_due_on, self.today + timedelta(days=1))

    async def test_postpone_care_task_on_an_overdue_task_counts_from_today_not_the_missed_date(self):
        await self.seed_care_schedule(
            plant_id=self.plant_id,
            task_type=CareTaskType.WATERING,
            interval_days=6,
            next_due_on=self.today - timedelta(days=5),
        )

        postponed = await self.postpone()

        self.assertEqual(postponed.next_due_on, self.today + timedelta(days=2))

    async def test_postpone_care_task_records_no_care_event_and_leaves_the_last_care_alone(self):
        await self.seed_care_schedule(
            plant_id=self.plant_id, task_type=CareTaskType.WATERING, interval_days=7, next_due_on=self.today
        )

        await self.postpone()

        self.assertEqual(await self.list_care_events(self.plant_id), [])
        schedule = await self.retrieve_care_schedule(self.plant_id, CareTaskType.WATERING)
        self.assertIsNone(schedule.last_performed_at)

    async def test_postpone_care_task_without_a_schedule_raises_does_not_exist(self):
        with self.assertRaises(DoesNotExistError) as context:
            await self.postpone()

        self.assertEqual(str(context.exception), "Plant 'Кактус' has no watering schedule")
