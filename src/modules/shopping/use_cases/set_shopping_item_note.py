from src.common.use_case import BaseUseCase
from src.modules.shopping.commands import SetShoppingItemNoteCommand
from src.modules.shopping.domain import ShoppingList
from src.modules.shopping.services.shopping_list_reader import load_priced_shopping_list


class SetShoppingItemNoteUseCase(BaseUseCase):
    """Attaches the detail a short name cannot hold — measurements, a link, a reminder of which one exactly"""

    async def __call__(self, command: SetShoppingItemNoteCommand) -> ShoppingList:
        async with self.uow as uow:
            item = await uow.shopping_items.retrieve_unbought(command.item_id)
            if item is not None:
                note = command.note.strip()
                await uow.shopping_items.update(item.id, {"note": note or None})

            return await load_priced_shopping_list(uow)
