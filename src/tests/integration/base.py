import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.infrastructure.db.base import Base
from src.infrastructure.db.main import apply_sqlite_pragmas
from src.infrastructure.db.models import CareEvent, CareSchedule, Plant, PlantClimateAlert, PlantPhoto
from src.infrastructure.db.uow import UnitOfWork
from src.tests.factories import (
    build_care_event_payload,
    build_care_schedule_payload,
    build_plant_payload,
    build_plant_photo_payload,
)
from src.tests.fakes import FrozenHouseholdCalendar

KYIV = ZoneInfo("Europe/Kyiv")

# 09:00 in Kyiv on 2026-07-12 — a fixed "now" keeps every due-date assertion unambiguous
FROZEN_NOW = datetime(2026, 7, 12, 6, 0, tzinfo=timezone.utc)


class BaseIntegrationTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
        apply_sqlite_pragmas(self.engine)
        self.session_factory = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        self.uow = UnitOfWork(session_factory=self.session_factory)
        self.household_calendar = FrozenHouseholdCalendar(timezone=KYIV, frozen_now=FROZEN_NOW)
        self.today = self.household_calendar.today()

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def seed_plant(self, **overrides) -> int:
        async with self.uow as uow:
            plant = Plant(**build_plant_payload(**overrides))
            uow.session.add(plant)
            await uow.session.flush()
            return plant.id

    async def seed_care_schedule(self, plant_id: int, **overrides) -> int:
        async with self.uow as uow:
            schedule = CareSchedule(**build_care_schedule_payload(plant_id=plant_id, **overrides))
            uow.session.add(schedule)
            await uow.session.flush()
            return schedule.id

    async def seed_care_event(self, plant_id: int, **overrides) -> int:
        async with self.uow as uow:
            event = CareEvent(**build_care_event_payload(plant_id=plant_id, **overrides))
            uow.session.add(event)
            await uow.session.flush()
            return event.id

    async def seed_plant_photo(self, plant_id: int, **overrides) -> int:
        async with self.uow as uow:
            photo = PlantPhoto(**build_plant_photo_payload(plant_id=plant_id, **overrides))
            uow.session.add(photo)
            await uow.session.flush()
            return photo.id

    async def seed_room_climate_readings(
        self,
        humidity_percent: float,
        since: datetime,
        until: datetime,
        temperature_celsius: float = 22.0,
    ) -> None:
        async with self.uow as uow:
            measured_at = since
            while measured_at <= until:
                await uow.room_climate_readings.create(
                    {
                        "temperature_celsius": temperature_celsius,
                        "relative_humidity_percent": humidity_percent,
                        "measured_at": measured_at,
                    }
                )
                measured_at += timedelta(hours=1)

    async def seed_plant_climate_alert(
        self, plant_id: int, dimension, status, value: float, notified_at: datetime
    ) -> None:
        async with self.uow as uow:
            await uow.plant_climate_alerts.create(
                {
                    "plant_id": plant_id,
                    "dimension": dimension,
                    "status": status,
                    "value": value,
                    "notified_at": notified_at,
                }
            )

    async def retrieve_plant_climate_alerts(self) -> list[PlantClimateAlert]:
        async with self.uow as uow:
            return list(await uow.plant_climate_alerts.list())

    async def retrieve_plant(self, plant_id: int) -> Plant:
        async with self.uow as uow:
            return await uow.plants.retrieve(plant_id)

    async def retrieve_care_schedule(self, plant_id: int, task_type) -> CareSchedule:
        async with self.uow as uow:
            return await uow.care_schedules.retrieve_for_plant(plant_id, task_type)

    async def remove_care_schedule(self, plant_id: int, task_type) -> None:
        """Drops the schedule while its care records stay, which is what removing a task from a plant leaves behind."""
        async with self.uow as uow:
            schedule = await uow.care_schedules.retrieve_for_plant(plant_id, task_type)
            await uow.care_schedules.delete(schedule.id)

    async def forget_previous_due_date(self, plant_id: int, task_type) -> None:
        """Reproduces a care record written before migration 012 started keeping the date it replaced."""
        async with self.uow as uow:
            event = await uow.care_events.retrieve_latest(plant_id, task_type)
            await uow.care_events.update(event.id, {"previous_next_due_on": None})

    async def list_care_events(self, plant_id: int) -> list[CareEvent]:
        async with self.uow as uow:
            return await uow.care_events.list_recent_by_plant_id(plant_id, limit=100)
