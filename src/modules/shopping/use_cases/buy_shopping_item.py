from src.common.time import current_time
from src.common.use_case import BaseActorUseCase
from src.modules.shopping.commands import BuyShoppingItemCommand
from src.modules.shopping.domain import ShoppingList
from src.modules.shopping.services.shopping_list_reader import load_priced_shopping_list


class BuyShoppingItemUseCase(BaseActorUseCase):
    async def __call__(self, command: BuyShoppingItemCommand) -> ShoppingList:
        async with self.uow as uow:
            # two people in the same shop tapping the same item is the normal case, not a conflict
            item = await uow.shopping_items.retrieve_unbought(command.item_id)
            if item is not None:
                await uow.shopping_items.update(
                    item.id,
                    {"bought_at": current_time(), "bought_by_display_name": self.actor.display_name},
                )

            return await load_priced_shopping_list(uow)
