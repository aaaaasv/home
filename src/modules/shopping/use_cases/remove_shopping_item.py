from src.common.use_case import BaseUseCase
from src.modules.shopping.commands import RemoveShoppingItemCommand
from src.modules.shopping.domain import ShoppingList
from src.modules.shopping.services.shopping_list_reader import load_priced_shopping_list


class RemoveShoppingItemUseCase(BaseUseCase):
    """Drops an item nobody intends to buy — unlike buying it, this leaves no trace"""

    async def __call__(self, command: RemoveShoppingItemCommand) -> ShoppingList:
        async with self.uow as uow:
            item = await uow.shopping_items.retrieve_unbought(command.item_id)
            if item is not None:
                await uow.shopping_items.delete(item.id)

            return await load_priced_shopping_list(uow)
