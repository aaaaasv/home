from datetime import date

from sqlalchemy import select

from src.infrastructure.db.models import CareDigestDelivery
from src.infrastructure.repositories.base import SQLAlchemyRepository


class CareDigestDeliveryRepository(SQLAlchemyRepository[CareDigestDelivery]):
    model = CareDigestDelivery

    async def retrieve_last_sent_date(self) -> date | None:
        result = await self.session.execute(select(CareDigestDelivery.sent_on).order_by(CareDigestDelivery.id.desc()))
        return result.scalars().first()

    async def record_sent(self, sent_on: date) -> None:
        await self.create({"sent_on": sent_on})
