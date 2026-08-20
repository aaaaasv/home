from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from src.infrastructure.db.models import AirConditionerRun
from src.infrastructure.db.uow import UnitOfWork
from src.modules.air_conditioner.domain import AirConditionerMode, AirConditionerState
from src.modules.air_conditioner.use_cases.evaluate_air_conditioner_runtime import EvaluateAirConditionerRuntimeUseCase
from src.tests.integration.base import BaseIntegrationTestCase

MOMENT = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
NOTIFY_AFTER = timedelta(hours=6)


def build_state(is_on: bool = True, room_temperature_celsius: int | None = 26) -> AirConditionerState:
    return AirConditionerState(
        is_on=is_on,
        mode=AirConditionerMode.COOL,
        target_temperature_celsius=24,
        room_temperature_celsius=room_temperature_celsius,
    )


class EvaluateAirConditionerRuntimeTestCase(BaseIntegrationTestCase):
    def evaluate(self):
        return EvaluateAirConditionerRuntimeUseCase(
            uow=UnitOfWork(session_factory=self.session_factory), notify_after=NOTIFY_AFTER
        )

    async def retrieve_runs(self) -> list[AirConditionerRun]:
        async with self.uow as uow:
            result = await uow.session.execute(select(AirConditionerRun).order_by(AirConditionerRun.id))
            return list(result.scalars().all())

    async def test_evaluate_runtime_when_the_unit_starts_opens_a_run_and_stays_silent(self):
        notice = await self.evaluate()(state=build_state(), moment=MOMENT)

        self.assertIsNone(notice)
        runs = await self.retrieve_runs()
        self.assertEqual(len(runs), 1)
        self.assertIsNone(runs[0].ended_at)

    async def test_evaluate_runtime_below_the_threshold_stays_silent(self):
        await self.evaluate()(state=build_state(), moment=MOMENT)

        notice = await self.evaluate()(state=build_state(), moment=MOMENT + timedelta(hours=5, minutes=59))

        self.assertIsNone(notice)

    async def test_evaluate_runtime_past_the_threshold_reports_the_hours_and_the_room(self):
        await self.evaluate()(state=build_state(), moment=MOMENT)

        notice = await self.evaluate()(state=build_state(), moment=MOMENT + timedelta(hours=6, minutes=30))

        self.assertEqual(notice.hours, 6)
        self.assertEqual(notice.room_temperature_celsius, 26)

    async def test_evaluate_runtime_reports_a_single_run_only_once(self):
        await self.evaluate()(state=build_state(), moment=MOMENT)
        await self.evaluate()(state=build_state(), moment=MOMENT + timedelta(hours=7))

        notice = await self.evaluate()(state=build_state(), moment=MOMENT + timedelta(hours=8))

        self.assertIsNone(notice)

    async def test_evaluate_runtime_when_the_unit_stops_closes_the_run(self):
        await self.evaluate()(state=build_state(), moment=MOMENT)

        await self.evaluate()(state=build_state(is_on=False), moment=MOMENT + timedelta(hours=2))

        runs = await self.retrieve_runs()
        self.assertEqual(runs[0].ended_at, MOMENT + timedelta(hours=2))

    async def test_evaluate_runtime_after_a_restart_of_the_unit_counts_from_the_new_start(self):
        await self.evaluate()(state=build_state(), moment=MOMENT)
        await self.evaluate()(state=build_state(is_on=False), moment=MOMENT + timedelta(hours=7))
        await self.evaluate()(state=build_state(), moment=MOMENT + timedelta(hours=8))

        notice = await self.evaluate()(state=build_state(), moment=MOMENT + timedelta(hours=13))

        self.assertIsNone(notice)
        self.assertEqual(len(await self.retrieve_runs()), 2)

    async def test_evaluate_runtime_reports_a_second_run_of_its_own(self):
        await self.evaluate()(state=build_state(), moment=MOMENT)
        await self.evaluate()(state=build_state(is_on=False), moment=MOMENT + timedelta(hours=1))
        await self.evaluate()(state=build_state(), moment=MOMENT + timedelta(hours=2))

        notice = await self.evaluate()(state=build_state(), moment=MOMENT + timedelta(hours=9))

        self.assertEqual(notice.hours, 7)

    async def test_evaluate_runtime_with_an_unreachable_unit_closes_the_run_and_stays_silent(self):
        await self.evaluate()(state=build_state(), moment=MOMENT)

        notice = await self.evaluate()(state=None, moment=MOMENT + timedelta(hours=7))

        self.assertIsNone(notice)
        runs = await self.retrieve_runs()
        self.assertEqual(runs[0].ended_at, MOMENT + timedelta(hours=7))

    async def test_evaluate_runtime_while_the_unit_stays_off_creates_nothing(self):
        notice = await self.evaluate()(state=build_state(is_on=False), moment=MOMENT)

        self.assertIsNone(notice)
        self.assertEqual(await self.retrieve_runs(), [])
