from datetime import date, datetime

from sqlalchemy import func, select

from src.infrastructure.db.models import RoomClimateAlert, RoomClimateDay, RoomClimateReading
from src.infrastructure.repositories.base import SQLAlchemyRepository


class RoomClimateReadingRepository(SQLAlchemyRepository[RoomClimateReading]):
    model = RoomClimateReading

    async def list_measured_since(self, moment: datetime) -> list[RoomClimateReading]:
        result = await self.session.execute(
            select(RoomClimateReading)
            .where(RoomClimateReading.measured_at >= moment)
            .order_by(RoomClimateReading.measured_at)
        )
        return list(result.scalars().all())

    async def retrieve_latest(self) -> RoomClimateReading | None:
        result = await self.session.execute(select(RoomClimateReading).order_by(RoomClimateReading.measured_at.desc()))
        return result.scalars().first()

    async def delete_measured_before(self, moment: datetime) -> None:
        for reading in await self._list_measured_before(moment):
            await self.session.delete(reading)

    async def _list_measured_before(self, moment: datetime) -> list[RoomClimateReading]:
        result = await self.session.execute(select(RoomClimateReading).where(RoomClimateReading.measured_at < moment))
        return list(result.scalars().all())

    async def list_hourly_averages(self, since: datetime) -> list[tuple[str, float, float]]:
        """Hourly means since a moment — thousands of raw readings are unplottable, one point an hour is not."""
        hour = func.strftime("%Y-%m-%d %H", RoomClimateReading.measured_at)
        result = await self.session.execute(
            select(
                hour,
                func.avg(RoomClimateReading.temperature_celsius),
                func.avg(RoomClimateReading.relative_humidity_percent),
            )
            .where(RoomClimateReading.measured_at >= since)
            .group_by(hour)
            .order_by(hour)
        )
        return [(stamp, round(temperature, 2), round(humidity, 2)) for stamp, temperature, humidity in result.all()]


class RoomClimateAlertRepository(SQLAlchemyRepository[RoomClimateAlert]):
    model = RoomClimateAlert

    async def retrieve_latest(self) -> RoomClimateAlert | None:
        result = await self.session.execute(select(RoomClimateAlert).order_by(RoomClimateAlert.id.desc()))
        return result.scalars().first()


class RoomClimateDayRepository(SQLAlchemyRepository[RoomClimateDay]):
    model = RoomClimateDay

    async def save_day(self, day: date, summary: dict) -> None:
        """One row per day, rewritten as the day fills — the last write of a day is the whole day."""
        existing = await self.session.get(RoomClimateDay, day)
        if existing is None:
            self.session.add(RoomClimateDay(day=day, **summary))
            return
        for field, value in summary.items():
            setattr(existing, field, value)

    async def list_between(self, first_day: date, last_day: date) -> list[RoomClimateDay]:
        result = await self.session.execute(
            select(RoomClimateDay)
            .where(RoomClimateDay.day >= first_day, RoomClimateDay.day <= last_day)
            .order_by(RoomClimateDay.day)
        )
        return list(result.scalars().all())
