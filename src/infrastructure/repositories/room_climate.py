from datetime import datetime

from sqlalchemy import select

from src.infrastructure.db.models import RoomClimateAlert, RoomClimateReading
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


class RoomClimateAlertRepository(SQLAlchemyRepository[RoomClimateAlert]):
    model = RoomClimateAlert

    async def retrieve_latest(self) -> RoomClimateAlert | None:
        result = await self.session.execute(select(RoomClimateAlert).order_by(RoomClimateAlert.id.desc()))
        return result.scalars().first()
