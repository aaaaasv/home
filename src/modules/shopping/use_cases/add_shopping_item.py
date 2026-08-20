from src.common.use_case import BaseActorUseCase
from src.modules.shopping.commands import AddShoppingItemCommand
from src.modules.shopping.domain import ShoppingList
from src.modules.shopping.services.shopping_list_reader import load_priced_shopping_list


class AddShoppingItemUseCase(BaseActorUseCase):
    async def __call__(self, command: AddShoppingItemCommand) -> ShoppingList:
        async with self.uow as uow:
            # writing "олія" twice is a family being a family, not an error — the second one is simply already there
            existing = await uow.shopping_items.retrieve_unbought_by_name(command.name)
            if existing is None:
                await uow.shopping_items.create(
                    {
                        "name": command.name,
                        "horizon": command.horizon,
                        "added_by_telegram_user_id": self.actor.telegram_user_id,
                        "added_by_display_name": self.actor.display_name,
                        "photo_telegram_file_id": command.photo_telegram_file_id,
                    }
                )
            elif command.photo_telegram_file_id is not None:
                # a photo captioned with a name already on the list attaches to that item rather than duplicating it
                await uow.shopping_items.update(existing.id, {"photo_telegram_file_id": command.photo_telegram_file_id})

            return await load_priced_shopping_list(uow)
