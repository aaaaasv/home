from datetime import datetime, timedelta, timezone

from src.infrastructure.db.models import ConservationRecord
from src.infrastructure.db.uow import UnitOfWork
from src.modules.power.domain import EcoFlowState
from src.modules.power.services.conservation import ConservationMode
from src.modules.power.use_cases.set_conservation_mode import SetConservationModeUseCase
from src.modules.power.use_cases.track_conservation import TrackConservationUseCase
from src.tests.integration.base import BaseIntegrationTestCase

NOW = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
CONSERVED_AFTER = timedelta(hours=6)


def build_state(battery_percent: float) -> EcoFlowState:
    return EcoFlowState(
        battery_percent=battery_percent,
        on_mains=True,
        ac_input_power=0,
        ac_output_power=0,
        ac_output_on=False,
        usb_output_on=False,
        dc_output_on=False,
        remaining_minutes=None,
        charge_limit_max=None,
        backup_reserve_percent=None,
        cell_temperature_celsius=None,
        as_of=NOW,
    )


class ConservationTestCase(BaseIntegrationTestCase):
    def track(self, now: datetime = NOW):
        return TrackConservationUseCase(
            uow=UnitOfWork(session_factory=self.session_factory), now=now, conserved_after=CONSERVED_AFTER
        )

    def set_mode(self, now: datetime = NOW):
        return SetConservationModeUseCase(uow=UnitOfWork(session_factory=self.session_factory), now=now)

    async def seed_record(self, **overrides) -> None:
        payload: dict = {
            "stored_percent": 60.0,
            "stored_at": NOW - timedelta(hours=1),
            "mode": ConservationMode.OFF.value,
            "is_conserved": False,
            "manual_override": False,
            "saw_low_since_cycle": False,
        }
        payload.update(overrides)
        async with self.uow as uow:
            uow.session.add(ConservationRecord(**payload))
            await uow.session.flush()

    async def retrieve_record(self) -> ConservationRecord | None:
        async with self.uow as uow:
            return await uow.conservation.get()


class TrackConservationTestCase(ConservationTestCase):
    async def test_track_conservation_without_a_record_and_an_unreachable_station_records_nothing(self):
        await self.track()(None)

        self.assertIsNone(await self.retrieve_record())

    async def test_track_conservation_without_a_record_and_a_reachable_station_baselines_the_charge(self):
        await self.track()(build_state(72.0))

        record = await self.retrieve_record()
        self.assertEqual(record.stored_percent, 72.0)
        self.assertEqual(record.stored_at, NOW)
        self.assertEqual(record.mode, ConservationMode.OFF.value)
        self.assertFalse(record.is_conserved)
        self.assertFalse(record.manual_override)
        self.assertFalse(record.saw_low_since_cycle)

    async def test_track_conservation_without_a_record_and_a_station_at_the_floor_remembers_the_low(self):
        await self.track()(build_state(4.0))

        record = await self.retrieve_record()
        self.assertTrue(record.saw_low_since_cycle)

    async def test_track_conservation_with_a_reachable_station_rebaselines_the_charge(self):
        await self.seed_record(stored_percent=40.0)

        await self.track()(build_state(58.0))

        record = await self.retrieve_record()
        self.assertEqual(record.stored_percent, 58.0)
        self.assertEqual(record.stored_at, NOW)
        self.assertIsNone(record.last_cycle_at)

    async def test_track_conservation_with_a_station_back_at_full_after_the_floor_closes_the_cycle(self):
        await self.seed_record(saw_low_since_cycle=True)

        await self.track()(build_state(96.0))

        record = await self.retrieve_record()
        self.assertEqual(record.last_cycle_at, NOW)
        self.assertFalse(record.saw_low_since_cycle)

    async def test_track_conservation_with_a_station_at_full_without_a_prior_low_leaves_the_cycle_open(self):
        await self.seed_record(saw_low_since_cycle=False)

        await self.track()(build_state(96.0))

        record = await self.retrieve_record()
        self.assertIsNone(record.last_cycle_at)
        self.assertFalse(record.saw_low_since_cycle)

    async def test_track_conservation_with_a_reachable_station_clears_an_automatic_conserved_mark(self):
        await self.seed_record(is_conserved=True, manual_override=False)

        await self.track()(build_state(61.0))

        record = await self.retrieve_record()
        self.assertFalse(record.is_conserved)
        self.assertFalse(record.manual_override)

    async def test_track_conservation_with_a_reachable_station_confirms_a_manual_in_use_mark(self):
        await self.seed_record(is_conserved=False, manual_override=True)

        await self.track()(build_state(61.0))

        record = await self.retrieve_record()
        self.assertFalse(record.is_conserved)
        self.assertFalse(record.manual_override)

    async def test_track_conservation_with_an_unreachable_station_inside_the_grace_window_keeps_it_in_use(self):
        await self.seed_record(stored_at=NOW - timedelta(hours=1))

        await self.track()(None)

        record = await self.retrieve_record()
        self.assertFalse(record.is_conserved)
        self.assertEqual(record.stored_at, NOW - timedelta(hours=1))

    async def test_track_conservation_with_an_unreachable_station_past_the_grace_window_marks_it_conserved(self):
        await self.seed_record(stored_at=NOW - timedelta(hours=7), stored_percent=55.0)

        await self.track()(None)

        record = await self.retrieve_record()
        self.assertTrue(record.is_conserved)
        self.assertEqual(record.stored_percent, 55.0)
        self.assertEqual(record.stored_at, NOW - timedelta(hours=7))

    async def test_track_conservation_with_an_unreachable_station_past_the_window_releases_a_manual_stored_mark(self):
        await self.seed_record(stored_at=NOW - timedelta(hours=7), is_conserved=True, manual_override=True)

        await self.track()(None)

        record = await self.retrieve_record()
        self.assertTrue(record.is_conserved)
        self.assertFalse(record.manual_override)

    async def test_track_conservation_with_an_unreachable_station_keeps_a_manual_in_use_mark(self):
        await self.seed_record(stored_at=NOW - timedelta(hours=7), is_conserved=False, manual_override=True)

        await self.track()(None)

        record = await self.retrieve_record()
        self.assertFalse(record.is_conserved)
        self.assertTrue(record.manual_override)


class SetConservationModeTestCase(ConservationTestCase):
    async def test_set_conservation_mode_to_stored_without_a_record_baselines_from_the_reading(self):
        await self.set_mode()(is_conserved=True, battery_percent=48.0)

        record = await self.retrieve_record()
        self.assertTrue(record.is_conserved)
        self.assertTrue(record.manual_override)
        self.assertEqual(record.stored_percent, 48.0)
        self.assertEqual(record.stored_at, NOW)
        self.assertEqual(record.mode, ConservationMode.OFF.value)
        self.assertFalse(record.saw_low_since_cycle)

    async def test_set_conservation_mode_to_stored_without_a_reading_baselines_at_the_storage_target(self):
        await self.set_mode()(is_conserved=True, battery_percent=None)

        record = await self.retrieve_record()
        self.assertEqual(record.stored_percent, 60.0)

    async def test_set_conservation_mode_to_stored_freezes_the_storage_clock_at_the_mark(self):
        await self.seed_record(stored_at=NOW - timedelta(days=3), stored_percent=70.0)

        await self.set_mode()(is_conserved=True, battery_percent=70.0)

        record = await self.retrieve_record()
        self.assertTrue(record.is_conserved)
        self.assertEqual(record.stored_at, NOW)
        self.assertEqual(record.stored_percent, 70.0)

    async def test_set_conservation_mode_to_in_use_leaves_the_storage_clock_alone(self):
        await self.seed_record(stored_at=NOW - timedelta(days=3), is_conserved=True)

        await self.set_mode()(is_conserved=False, battery_percent=70.0)

        record = await self.retrieve_record()
        self.assertFalse(record.is_conserved)
        self.assertTrue(record.manual_override)
        self.assertEqual(record.stored_at, NOW - timedelta(days=3))
