from src.common.use_case import BaseUseCase
from src.modules.shopping.domain import ShoppingList
from src.modules.shopping.services.shopping_list_reader import load_priced_shopping_list


class RetrieveShoppingListUseCase(BaseUseCase):
    async def __call__(self) -> ShoppingList:
        async with self.uow as uow:
            return await load_priced_shopping_list(uow)
