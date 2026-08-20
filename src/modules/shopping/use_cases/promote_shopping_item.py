from src.common.use_case import BaseUseCase
from src.modules.shopping.commands import PromoteShoppingItemCommand
from src.modules.shopping.constants import ShoppingHorizon
from src.modules.shopping.domain import ShoppingList
from src.modules.shopping.services.shopping_list_reader import load_priced_shopping_list


class PromoteShoppingItemUseCase(BaseUseCase):
    """Moves a someday item into the next trip"""

    async def __call__(self, command: PromoteShoppingItemCommand) -> ShoppingList:
        async with self.uow as uow:
            item = await uow.shopping_items.retrieve_unbought(command.item_id)
            if item is not None:
                await uow.shopping_items.update(item.id, {"horizon": ShoppingHorizon.NOW})

            return await load_priced_shopping_list(uow)
