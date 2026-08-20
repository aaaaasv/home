from src.common.use_case import BaseUseCase
from src.modules.shopping.commands import SetShoppingItemPhotoCommand
from src.modules.shopping.domain import ShoppingList
from src.modules.shopping.services.shopping_list_reader import load_priced_shopping_list


class SetShoppingItemPhotoUseCase(BaseUseCase):
    """Attaches (or replaces) the photo on an item added earlier by text"""

    async def __call__(self, command: SetShoppingItemPhotoCommand) -> ShoppingList:
        async with self.uow as uow:
            item = await uow.shopping_items.retrieve_unbought(command.item_id)
            if item is not None:
                await uow.shopping_items.update(item.id, {"photo_telegram_file_id": command.photo_telegram_file_id})

            return await load_priced_shopping_list(uow)
