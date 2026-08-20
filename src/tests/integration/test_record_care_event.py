from datetime import date, datetime, timedelta, timezone

from src.common.constants import CareTaskType
from src.common.exceptions import DoesNotExistError, RecentCareExistsError
from src.modules.plant_care.commands import RecordCareEventCommand
from src.modules.plant_care.use_cases.record_care_event import RecordCareEventUseCase
from src.tests.factories import OWNER, PARTNER
from src.tests.integration.base import FROZEN_NOW, BaseIntegrationTestCase

RECENT_CARE_GUARD_HOURS = 12


class RecordCareEventTestCase(BaseIntegrationTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.plant_id = await self.seed_plant(name="Монстера")
        await self.seed_care_schedule(
            plant_id=self.plant_id,
            task_type=CareTaskType.WATERING,
            interval_days=5,
            next_due_on=self.today,
        )

    def build_use_case(self, actor=OWNER) -> RecordCareEventUseCase:
        return RecordCareEventUseCase(
            uow=self.uow,
            actor=actor,
            household_calendar=self.household_calendar,
            recent_care_guard_hours=RECENT_CARE_GUARD_HOURS,
        )

    async def test_record_care_event_success(self):
        command = RecordCareEventCommand(
            plant_id=self.plant_id, task_type=CareTaskType.WATERING, performed_at=FROZEN_NOW
        )

        record = await self.build_use_case(actor=PARTNER)(command)

        self.assertEqual(record.plant_name, "Монстера")
        self.assertEqual(record.task_type, CareTaskType.WATERING)
        self.assertEqual(record.performed_by_display_name, "Марта")
        self.assertEqual(record.next_due_on, date(2026, 7, 17))

    async def test_record_care_event_reschedules_the_next_watering_from_the_actual_care(self):
        watered_two_days_early = FROZEN_NOW - timedelta(days=2)
        command = RecordCareEventCommand(
            plant_id=self.plant_id, task_type=CareTaskType.WATERING, performed_at=watered_two_days_early
        )

        await self.build_use_case()(command)

        schedule = await self.retrieve_care_schedule(self.plant_id, CareTaskType.WATERING)
        self.assertEqual(schedule.next_due_on, date(2026, 7, 15))
        self.assertEqual(schedule.last_performed_at, watered_two_days_early)

    async def test_record_care_event_within_the_guard_window_raises_recent_care_exists(self):
        await self.seed_care_event(
            plant_id=self.plant_id,
            task_type=CareTaskType.WATERING,
            performed_at=FROZEN_NOW - timedelta(hours=2),
            performed_by=PARTNER,
        )
        command = RecordCareEventCommand(
            plant_id=self.plant_id, task_type=CareTaskType.WATERING, performed_at=FROZEN_NOW
        )

        with self.assertRaises(RecentCareExistsError) as context:
            await self.build_use_case()(command)

        self.assertEqual(
            str(context.exception),
            "Plant 'Монстера' already had watering from Марта within the last 12 hours",
        )
        self.assertEqual(context.exception.plant_name, "Монстера")
        self.assertEqual(context.exception.performed_by_display_name, "Марта")
        self.assertEqual(context.exception.performed_at, FROZEN_NOW - timedelta(hours=2))

    async def test_record_care_event_within_the_guard_window_keeps_the_schedule_untouched(self):
        await self.seed_care_event(
            plant_id=self.plant_id, task_type=CareTaskType.WATERING, performed_at=FROZEN_NOW - timedelta(hours=2)
        )
        command = RecordCareEventCommand(
            plant_id=self.plant_id, task_type=CareTaskType.WATERING, performed_at=FROZEN_NOW
        )

        with self.assertRaises(RecentCareExistsError):
            await self.build_use_case()(command)

        schedule = await self.retrieve_care_schedule(self.plant_id, CareTaskType.WATERING)
        self.assertEqual(schedule.next_due_on, self.today)
        self.assertIsNone(schedule.last_performed_at)
        self.assertEqual(len(await self.list_care_events(self.plant_id)), 1)

    async def test_record_care_event_within_the_guard_window_with_force_records_the_second_event(self):
        await self.seed_care_event(
            plant_id=self.plant_id, task_type=CareTaskType.WATERING, performed_at=FROZEN_NOW - timedelta(hours=2)
        )
        command = RecordCareEventCommand(
            plant_id=self.plant_id, task_type=CareTaskType.WATERING, performed_at=FROZEN_NOW, force=True
        )

        record = await self.build_use_case()(command)

        self.assertEqual(record.next_due_on, date(2026, 7, 17))
        self.assertEqual(len(await self.list_care_events(self.plant_id)), 2)

    async def test_record_care_event_after_the_guard_window_records_the_second_event(self):
        await self.seed_care_event(
            plant_id=self.plant_id,
            task_type=CareTaskType.WATERING,
            performed_at=FROZEN_NOW - timedelta(hours=RECENT_CARE_GUARD_HOURS),
        )
        command = RecordCareEventCommand(
            plant_id=self.plant_id, task_type=CareTaskType.WATERING, performed_at=FROZEN_NOW
        )

        record = await self.build_use_case()(command)

        self.assertEqual(record.next_due_on, date(2026, 7, 17))
        self.assertEqual(len(await self.list_care_events(self.plant_id)), 2)

    async def test_record_care_event_for_another_task_ignores_the_watering_guard(self):
        await self.seed_care_schedule(
            plant_id=self.plant_id, task_type=CareTaskType.FERTILIZING, interval_days=30, next_due_on=self.today
        )
        await self.seed_care_event(
            plant_id=self.plant_id, task_type=CareTaskType.WATERING, performed_at=FROZEN_NOW - timedelta(hours=1)
        )
        command = RecordCareEventCommand(
            plant_id=self.plant_id, task_type=CareTaskType.FERTILIZING, performed_at=FROZEN_NOW
        )

        record = await self.build_use_case()(command)

        self.assertEqual(record.task_type, CareTaskType.FERTILIZING)
        self.assertEqual(record.next_due_on, date(2026, 8, 11))

    async def test_record_care_event_for_a_missing_plant_raises_does_not_exist(self):
        command = RecordCareEventCommand(plant_id=999, task_type=CareTaskType.WATERING, performed_at=FROZEN_NOW)

        with self.assertRaises(DoesNotExistError) as context:
            await self.build_use_case()(command)

        self.assertEqual(str(context.exception), "Plant 999 not found")

    async def test_record_care_event_for_an_unscheduled_task_raises_does_not_exist(self):
        command = RecordCareEventCommand(
            plant_id=self.plant_id, task_type=CareTaskType.REPOTTING, performed_at=FROZEN_NOW
        )

        with self.assertRaises(DoesNotExistError) as context:
            await self.build_use_case()(command)

        self.assertEqual(str(context.exception), "Plant 'Монстера' has no repotting schedule")

    async def test_record_care_event_late_in_the_kyiv_evening_uses_the_local_day(self):
        late_evening_in_kyiv = datetime(2026, 7, 12, 21, 30, tzinfo=timezone.utc)
        command = RecordCareEventCommand(
            plant_id=self.plant_id, task_type=CareTaskType.WATERING, performed_at=late_evening_in_kyiv
        )

        record = await self.build_use_case()(command)

        self.assertEqual(record.next_due_on, date(2026, 7, 18))
