from datetime import date, datetime

from sqlalchemy import select

from src.infrastructure.db.models import SensorDay, SensorReading
from src.infrastructure.repositories.base import SQLAlchemyRepository


class SensorReadingRepository(SQLAlchemyRepository[SensorReading]):
    model = SensorReading

    async def list_measured_between(self, sensor: str, first: datetime, last: datetime) -> list[SensorReading]:
        result = await self.session.execute(
            select(SensorReading)
            .where(
                SensorReading.sensor == sensor,
                SensorReading.measured_at >= first,
                SensorReading.measured_at < last,
            )
            .order_by(SensorReading.measured_at)
        )
        return list(result.scalars().all())

    async def list_sensors_measured_since(self, moment: datetime) -> list[str]:
        """Which sensors have said anything since a moment — the fold only visits those, not a configured list."""
        result = await self.session.execute(
            select(SensorReading.sensor).where(SensorReading.measured_at >= moment).distinct()
        )
        return list(result.scalars().all())

    async def retrieve_latest(self, sensor: str) -> SensorReading | None:
        result = await self.session.execute(
            select(SensorReading).where(SensorReading.sensor == sensor).order_by(SensorReading.measured_at.desc())
        )
        return result.scalars().first()

    async def delete_measured_before(self, moment: datetime) -> None:
        for reading in await self._list_measured_before(moment):
            await self.session.delete(reading)

    async def _list_measured_before(self, moment: datetime) -> list[SensorReading]:
        result = await self.session.execute(select(SensorReading).where(SensorReading.measured_at < moment))
        return list(result.scalars().all())


class SensorDayRepository(SQLAlchemyRepository[SensorDay]):
    model = SensorDay

    async def save_day(self, sensor: str, day: date, summary: dict) -> None:
        """One row per sensor per day, rewritten as the day fills — the last write of a day is the whole day."""
        existing = await self.session.get(SensorDay, (sensor, day))
        if existing is None:
            self.session.add(SensorDay(sensor=sensor, day=day, **summary))
            return
        for field, value in summary.items():
            setattr(existing, field, value)

    async def list_between(self, sensor: str, first_day: date, last_day: date) -> list[SensorDay]:
        result = await self.session.execute(
            select(SensorDay)
            .where(SensorDay.sensor == sensor, SensorDay.day >= first_day, SensorDay.day <= last_day)
            .order_by(SensorDay.day)
        )
        return list(result.scalars().all())
