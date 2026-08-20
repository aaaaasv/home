from src.common.use_case import BaseUseCase
from src.modules.shopping.commands import RenameShoppingItemCommand
from src.modules.shopping.domain import ShoppingList
from src.modules.shopping.services.shopping_list_reader import load_priced_shopping_list


class RenameShoppingItemUseCase(BaseUseCase):
    """Fixes an item's name — a typo, or a clearer wording — without touching anything else about it"""

    async def __call__(self, command: RenameShoppingItemCommand) -> ShoppingList:
        async with self.uow as uow:
            item = await uow.shopping_items.retrieve_unbought(command.item_id)
            if item is not None:
                await uow.shopping_items.update(item.id, {"name": command.name.strip()})

            return await load_priced_shopping_list(uow)
