from src.bot.handlers.shopping.formatting import render_shopping_list
from src.bot.handlers.shopping.keyboards import build_shopping_list_keyboard
from src.bot.services.posted_message_tracker import SHOPPING_LIST_KIND
from src.bot.services.single_message_board import SingleMessageBoard
from src.modules.shopping.domain import ShoppingList

SHOPPING_MODULE_NAME = "shopping"


class ShoppingListBoard(SingleMessageBoard):
    """Keeps the whole list in one message: edited in place while Telegram allows it, reposted once it does not."""

    kind = SHOPPING_LIST_KIND

    def render(self, shopping_list: ShoppingList) -> str:
        return render_shopping_list(shopping_list)

    def build_keyboard(self, shopping_list: ShoppingList):
        return build_shopping_list_keyboard(shopping_list)
