"""Turns the shopping list into facts a model can answer from."""
from src.bot.services.household_facts import FactsContext
from src.modules.shopping.domain import ShoppingItemDetails, ShoppingList
from src.modules.shopping.use_cases.retrieve_shopping_list import RetrieveShoppingListUseCase


async def gather_facts(context: FactsContext) -> str:
    """Both horizons: what the next trip needs, and the someday list with the prices being watched."""
    return render_shopping_facts(await RetrieveShoppingListUseCase(uow=context.uow_factory())())


def render_shopping_facts(shopping_list: ShoppingList) -> str:
    if shopping_list.is_empty:
        return ""
    lines = ["Список покупок:"]
    lines.extend(f"— треба купити: {item.name}{_render_note(item)}" for item in shopping_list.needed_now)
    lines.extend(
        f"— колись: {item.name}{_render_price(item)}{_render_note(item)}" for item in shopping_list.wanted_later
    )
    return "\n".join(lines)


def _render_price(item: ShoppingItemDetails) -> str:
    return f", ціна зараз {item.current_price} ₴" if item.is_tracked else ""


def _render_note(item: ShoppingItemDetails) -> str:
    return f" ({item.note})" if item.has_note else ""
