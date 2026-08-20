from datetime import datetime

from src.common.domain import Actor
from src.common.exceptions import ValidationError
from src.common.use_case import BaseActorUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.shopping.commands import TrackShoppingItemCommand
from src.modules.shopping.constants import TRACKED_ITEM_NAME_MAX_LENGTH, ShoppingHorizon
from src.modules.shopping.domain import ShoppingList, TrackedProduct
from src.modules.shopping.services.price_source import PriceSource, is_hotline_url
from src.modules.shopping.services.shopping_list_reader import load_priced_shopping_list


class TrackShoppingItemUseCase(BaseActorUseCase):
    """Reads a hotline product page and adds it to the someday list under price watch"""

    def __init__(self, uow: UnitOfWork, actor: Actor, price_source: PriceSource, checked_at: datetime):
        super().__init__(uow, actor)
        self.price_source = price_source
        self.checked_at = checked_at

    async def __call__(self, command: TrackShoppingItemCommand) -> ShoppingList:
        url = command.hotline_url.strip()
        if not is_hotline_url(url):
            raise ValidationError("Only hotline.ua links can be tracked")

        product = await self.price_source.fetch(url)
        if product is None:
            raise ValidationError("Could not read the product page")

        async with self.uow as uow:
            # adding the same link twice is the same family habit as writing "олія" twice — the first one stands
            if await uow.shopping_items.retrieve_unbought_by_url(url) is None:
                item = await uow.shopping_items.create(
                    {
                        "name": _shorten(product),
                        "horizon": ShoppingHorizon.LATER,
                        "hotline_url": url,
                        "added_by_telegram_user_id": self.actor.telegram_user_id,
                        "added_by_display_name": self.actor.display_name,
                    }
                )
                await uow.price_checks.record(item.id, product.price, self.checked_at)

            return await load_priced_shopping_list(uow)


def _shorten(product: TrackedProduct) -> str:
    if len(product.name) <= TRACKED_ITEM_NAME_MAX_LENGTH:
        return product.name
    return product.name[: TRACKED_ITEM_NAME_MAX_LENGTH - 1].rstrip() + "…"
