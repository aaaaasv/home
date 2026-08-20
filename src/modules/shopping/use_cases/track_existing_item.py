from datetime import datetime

from src.common.exceptions import DoesNotExistError, ValidationError
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.shopping.commands import TrackExistingItemCommand
from src.modules.shopping.domain import TrackedProduct
from src.modules.shopping.services.price_source import PriceSource, is_hotline_url


class TrackExistingItemUseCase(BaseUseCase):
    """Attaches price watch to an item already on the list, keeping the family's own short name for it"""

    def __init__(self, uow: UnitOfWork, price_source: PriceSource, checked_at: datetime):
        super().__init__(uow)
        self.price_source = price_source
        self.checked_at = checked_at

    async def __call__(self, command: TrackExistingItemCommand) -> TrackedProduct:
        url = command.hotline_url.strip()
        if not is_hotline_url(url):
            raise ValidationError("Only hotline.ua links can be tracked")

        product = await self.price_source.fetch(url)
        if product is None:
            raise ValidationError("Could not read the product page")

        async with self.uow as uow:
            item = await uow.shopping_items.retrieve_unbought(command.item_id)
            if item is None:
                raise DoesNotExistError(f"Shopping item {command.item_id} not found")

            await uow.shopping_items.update(item.id, {"hotline_url": url})
            await uow.price_checks.record(item.id, product.price, self.checked_at)

        return product
