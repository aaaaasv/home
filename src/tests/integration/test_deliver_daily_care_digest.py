from datetime import time, timedelta

from src.common.constants import CareTaskType
from src.modules.plant_care.use_cases.deliver_daily_care_digest import DeliverDailyCareDigestUseCase
from src.tests.fakes import FrozenHouseholdCalendar
from src.tests.integration.base import FROZEN_NOW, KYIV, BaseIntegrationTestCase

# the frozen clock sits at 09:00 Kyiv, so these two bracket "now"
BEFORE_NOW = time(8, 0)
AFTER_NOW = time(10, 0)


class DeliverDailyCareDigestTestCase(BaseIntegrationTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.plant_id = await self.seed_plant(name="Кактус")
        await self.seed_care_schedule(
            plant_id=self.plant_id, task_type=CareTaskType.WATERING, interval_days=3, next_due_on=self.today
        )

    def build_use_case(self, digest_time: time) -> DeliverDailyCareDigestUseCase:
        return DeliverDailyCareDigestUseCase(
            uow=self.uow, household_calendar=self.household_calendar, digest_time=digest_time
        )

    async def record_digest_sent(self, sent_on) -> None:
        async with self.uow as uow:
            await uow.care_digest_deliveries.record_sent(sent_on)

    async def test_deliver_before_the_digest_time_returns_nothing(self):
        digest = await self.build_use_case(digest_time=AFTER_NOW)()

        self.assertIsNone(digest)

    async def test_deliver_after_the_digest_time_when_unsent_returns_todays_digest(self):
        digest = await self.build_use_case(digest_time=BEFORE_NOW)()

        self.assertEqual(digest.today, self.today)
        self.assertEqual([task.plant_name for task in digest.tasks], ["Кактус"])

    async def test_deliver_when_already_sent_today_returns_nothing(self):
        await self.record_digest_sent(self.today)

        digest = await self.build_use_case(digest_time=BEFORE_NOW)()

        self.assertIsNone(digest)

    async def test_deliver_when_it_was_sent_yesterday_returns_todays_digest(self):
        await self.record_digest_sent(self.today - timedelta(days=1))

        digest = await self.build_use_case(digest_time=BEFORE_NOW)()

        self.assertEqual([task.plant_name for task in digest.tasks], ["Кактус"])

    async def test_deliver_when_nothing_is_due_returns_nothing(self):
        async with self.uow as uow:
            schedule = await uow.care_schedules.retrieve_for_plant(self.plant_id, CareTaskType.WATERING)
            await uow.care_schedules.update(schedule.id, {"next_due_on": self.today + timedelta(days=2)})

        digest = await self.build_use_case(digest_time=BEFORE_NOW)()

        self.assertIsNone(digest)


class WeekendDigestTimeTestCase(BaseIntegrationTestCase):
    """FROZEN_NOW is a Sunday, so the weekend branch is the one exercised unless the calendar is moved."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        plant_id = await self.seed_plant(name="Кактус")
        # overdue rather than due today, so it is still due when a test moves the clock back to a weekday
        await self.seed_care_schedule(
            plant_id=plant_id,
            task_type=CareTaskType.WATERING,
            interval_days=7,
            next_due_on=self.today - timedelta(days=10),
        )

    def build_use_case(self, digest_time, weekend_digest_time, frozen_now=FROZEN_NOW):
        return DeliverDailyCareDigestUseCase(
            uow=self.uow,
            household_calendar=FrozenHouseholdCalendar(timezone=KYIV, frozen_now=frozen_now),
            digest_time=digest_time,
            weekend_digest_time=weekend_digest_time,
        )

    async def test_deliver_on_a_weekend_before_the_weekend_time_returns_nothing(self):
        digest = await self.build_use_case(digest_time=BEFORE_NOW, weekend_digest_time=AFTER_NOW)()

        self.assertIsNone(digest)

    async def test_deliver_on_a_weekend_after_the_weekend_time_returns_the_digest(self):
        digest = await self.build_use_case(digest_time=AFTER_NOW, weekend_digest_time=BEFORE_NOW)()

        self.assertIsNotNone(digest)

    async def test_deliver_on_a_weekday_ignores_the_weekend_time(self):
        wednesday = FROZEN_NOW - timedelta(days=4)

        digest = await self.build_use_case(
            digest_time=BEFORE_NOW, weekend_digest_time=AFTER_NOW, frozen_now=wednesday
        )()

        self.assertIsNotNone(digest)

    async def test_deliver_with_no_weekend_time_falls_back_to_the_weekday_time(self):
        digest = await self.build_use_case(digest_time=BEFORE_NOW, weekend_digest_time=None)()

        self.assertIsNotNone(digest)
