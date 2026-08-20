from datetime import date, datetime, timezone

from src.common.constants import CareTaskType
from src.modules.plant_care.use_cases.build_care_digest import BuildCareDigestUseCase
from src.tests.fakes import FrozenHouseholdCalendar
from src.tests.integration.base import KYIV, BaseIntegrationTestCase

# a fertilizing season of April–September; the plants that eat only in the warm half of the year live inside it
FERTILIZING_SEASON = {"season_start_month": 4, "season_end_month": 9}


class SeasonalCareDigestTestCase(BaseIntegrationTestCase):
    def build_use_case_at(self, moment: datetime) -> BuildCareDigestUseCase:
        calendar = FrozenHouseholdCalendar(timezone=KYIV, frozen_now=moment)
        return BuildCareDigestUseCase(uow=self.uow, household_calendar=calendar)

    async def test_build_care_digest_off_season_omits_a_due_fertilizing_task(self):
        plant_id = await self.seed_plant(name="Алое")
        await self.seed_care_schedule(
            plant_id=plant_id,
            task_type=CareTaskType.FERTILIZING,
            next_due_on=date(2026, 10, 4),
            **FERTILIZING_SEASON,
        )

        digest = await self.build_use_case_at(datetime(2027, 1, 15, 12, 0, tzinfo=timezone.utc))()

        self.assertEqual(digest.today, date(2027, 1, 15))
        self.assertEqual(digest.tasks, [])

    async def test_build_care_digest_in_season_reports_a_due_fertilizing_task(self):
        plant_id = await self.seed_plant(name="Алое")
        await self.seed_care_schedule(
            plant_id=plant_id,
            task_type=CareTaskType.FERTILIZING,
            next_due_on=date(2026, 7, 9),
            **FERTILIZING_SEASON,
        )

        digest = await self.build_use_case_at(datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc))()

        self.assertEqual(len(digest.tasks), 1)
        self.assertEqual(digest.tasks[0].plant_name, "Алое")
        self.assertEqual(digest.tasks[0].task_type, CareTaskType.FERTILIZING)
        self.assertEqual(digest.tasks[0].overdue_days, 3)

    async def test_build_care_digest_at_season_start_reads_an_overwintered_task_as_due_today(self):
        plant_id = await self.seed_plant(name="Алое")
        await self.seed_care_schedule(
            plant_id=plant_id,
            task_type=CareTaskType.FERTILIZING,
            next_due_on=date(2026, 10, 4),
            **FERTILIZING_SEASON,
        )

        digest = await self.build_use_case_at(datetime(2027, 4, 1, 12, 0, tzinfo=timezone.utc))()

        self.assertEqual(len(digest.tasks), 1)
        self.assertEqual(digest.tasks[0].plant_name, "Алое")
        self.assertEqual(digest.tasks[0].overdue_days, 0)

    async def test_build_care_digest_off_season_still_reports_a_due_watering_task(self):
        plant_id = await self.seed_plant(name="Містер Біг")
        await self.seed_care_schedule(plant_id=plant_id, task_type=CareTaskType.WATERING, next_due_on=date(2027, 1, 15))

        digest = await self.build_use_case_at(datetime(2027, 1, 15, 12, 0, tzinfo=timezone.utc))()

        self.assertEqual(len(digest.tasks), 1)
        self.assertEqual(digest.tasks[0].task_type, CareTaskType.WATERING)
        self.assertEqual(digest.tasks[0].overdue_days, 0)

    async def test_build_care_digest_before_the_season_month_omits_the_task(self):
        plant_id = await self.seed_plant(name="Містер Біг")
        await self.seed_care_schedule(
            plant_id=plant_id,
            task_type=CareTaskType.FERTILIZING,
            next_due_on=date(2027, 3, 20),
            season_start_month=5,
            season_end_month=9,
        )

        digest = await self.build_use_case_at(datetime(2027, 4, 20, 12, 0, tzinfo=timezone.utc))()

        self.assertEqual(digest.tasks, [])
