from datetime import date, datetime

from sqlalchemy import func, select

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

    async def list_room_measured_since(self, room: str, moment: datetime) -> list[SensorReading]:
        """Every reading from every sensor that speaks for one room — two sensors in a room are one air."""
        result = await self.session.execute(
            select(SensorReading)
            .where(SensorReading.room == room, SensorReading.measured_at >= moment)
            .order_by(SensorReading.measured_at)
        )
        return list(result.scalars().all())

    async def list_sensors_measured_since(self, moment: datetime) -> list[str]:
        """Which sensors have said anything since a moment — the fold only visits those, not a configured list."""
        result = await self.session.execute(
            select(SensorReading.sensor).where(SensorReading.measured_at >= moment).distinct()
        )
        return list(result.scalars().all())

    async def average_between(
        self, sensors: set[str], first: datetime, last: datetime
    ) -> tuple[float | None, float | None]:
        """Mean temperature and humidity across several sensors over a window, as a trend needs them."""
        if not sensors:
            return None, None
        result = await self.session.execute(
            select(
                func.avg(SensorReading.temperature_celsius),
                func.avg(SensorReading.relative_humidity_percent),
            ).where(
                SensorReading.sensor.in_(sensors),
                SensorReading.measured_at >= first,
                SensorReading.measured_at < last,
            )
        )
        temperature, humidity = result.one()
        return temperature, humidity

    async def list_hourly_averages_for_room(self, room: str, since: datetime) -> list[tuple[str, float, float]]:
        """Hourly means for one room — thousands of raw readings are unplottable, one point an hour is not."""
        hour = func.strftime("%Y-%m-%d %H", SensorReading.measured_at)
        result = await self.session.execute(
            select(
                hour,
                func.avg(SensorReading.temperature_celsius),
                func.avg(SensorReading.relative_humidity_percent),
            )
            .where(
                SensorReading.room == room,
                SensorReading.measured_at >= since,
                SensorReading.temperature_celsius.isnot(None),
            )
            .group_by(hour)
            .order_by(hour)
        )
        return [(stamp, round(temperature, 2), round(humidity or 0.0, 2)) for stamp, temperature, humidity in result]

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

    async def list_room_between(self, room: str, first_day: date, last_day: date) -> list[SensorDay]:
        """Every day every sensor of one room folded — two sensors in a room describe one air, as elsewhere."""
        result = await self.session.execute(
            select(SensorDay)
            .where(SensorDay.room == room, SensorDay.day >= first_day, SensorDay.day <= last_day)
            .order_by(SensorDay.day)
        )
        return list(result.scalars().all())

    async def list_between(self, sensor: str, first_day: date, last_day: date) -> list[SensorDay]:
        result = await self.session.execute(
            select(SensorDay)
            .where(SensorDay.sensor == sensor, SensorDay.day >= first_day, SensorDay.day <= last_day)
            .order_by(SensorDay.day)
        )
        return list(result.scalars().all())
