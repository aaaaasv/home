from datetime import datetime

from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.shopping.domain import PriceCheckOutcome, PriceDropAnnouncement
from src.modules.shopping.services.price_source import PriceSource


class CheckTrackedPricesUseCase(BaseUseCase):
    """Re-reads every tracked item and reports the ones that just reached a new low since watching began"""

    def __init__(self, uow: UnitOfWork, price_source: PriceSource, checked_at: datetime):
        super().__init__(uow)
        self.price_source = price_source
        self.checked_at = checked_at

    async def __call__(self) -> PriceCheckOutcome:
        async with self.uow as uow:
            tracked = await uow.shopping_items.list_tracked()

        drops = []
        failures = []
        for item in tracked:
            product = await self.price_source.fetch(item.hotline_url)
            if product is None:
                failures.append(item.name)
                continue

            async with self.uow as uow:
                previous_low = await uow.price_checks.retrieve_minimum(item.id)
                await uow.price_checks.record(item.id, product.price, self.checked_at)

            if previous_low is not None and product.price < previous_low:
                drops.append(
                    PriceDropAnnouncement(
                        name=item.name,
                        hotline_url=item.hotline_url,
                        previous_low=previous_low,
                        new_price=product.price,
                        shop=product.shop,
                        rating=product.rating,
                        buy_link=product.buy_link,
                    )
                )

        return PriceCheckOutcome(drops=drops, failures=failures)
