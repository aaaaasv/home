from src.infrastructure.db.uow import UnitOfWork
from src.modules.shopping.domain import ShoppingList


async def load_priced_shopping_list(uow: UnitOfWork) -> ShoppingList:
    """The whole list with the latest and first-seen price attached to every tracked item"""
    items = await uow.shopping_items.list_unbought()
    current_prices = {}
    initial_prices = {}
    for item in items:
        if item.hotline_url is None:
            continue
        current_prices[item.id] = await uow.price_checks.retrieve_latest(item.id)
        initial_prices[item.id] = await uow.price_checks.retrieve_initial(item.id)
    return ShoppingList.from_items(items, current_prices, initial_prices)
