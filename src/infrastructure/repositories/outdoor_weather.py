from datetime import date

from sqlalchemy import select

from src.infrastructure.db.models import OutdoorWeatherDay
from src.infrastructure.repositories.base import SQLAlchemyRepository


class OutdoorWeatherDayRepository(SQLAlchemyRepository[OutdoorWeatherDay]):
    model = OutdoorWeatherDay

    async def retrieve_day(self, day: date) -> OutdoorWeatherDay | None:
        return await self.session.get(OutdoorWeatherDay, day)

    async def save_day(self, day: date, summary: dict) -> None:
        """One row per day, rewritten as the day fills — the last write of a day is the whole day."""
        existing = await self.session.get(OutdoorWeatherDay, day)
        if existing is None:
            self.session.add(OutdoorWeatherDay(day=day, **summary))
            return
        for field, value in summary.items():
            setattr(existing, field, value)

    async def list_between(self, first_day: date, last_day: date) -> list[OutdoorWeatherDay]:
        result = await self.session.execute(
            select(OutdoorWeatherDay)
            .where(OutdoorWeatherDay.day >= first_day, OutdoorWeatherDay.day <= last_day)
            .order_by(OutdoorWeatherDay.day)
        )
        return list(result.scalars().all())
