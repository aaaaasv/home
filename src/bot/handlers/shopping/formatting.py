"""How the shopping list and its price alerts render."""
from html import escape

from src.bot.handlers.shopping.messages import (
    PRICE_DROP_ALERT,
    PRICE_DROP_SHOP,
    PRICE_DROP_SHOP_RATING,
    PRICE_TREND_ARROWS,
    PRICE_WATCH_BROKEN,
    SHOPPING_LIST_EMPTY,
    SHOPPING_LIST_TITLE,
    SHOPPING_NEEDED_NOW,
    SHOPPING_WANTED_LATER,
)
from src.modules.shopping.domain import PriceDropAnnouncement, ShoppingItemDetails, ShoppingList


def render_shopping_list(shopping_list: ShoppingList) -> str:
    if shopping_list.is_empty:
        return SHOPPING_LIST_EMPTY

    lines = [SHOPPING_LIST_TITLE]
    if shopping_list.needed_now:
        lines.extend(["", SHOPPING_NEEDED_NOW])
        lines.extend(
            f"☐ {escape(item.name)} · {escape(item.added_by_display_name)}" for item in shopping_list.needed_now
        )

    if shopping_list.wanted_later:
        # the someday list is reference that grows over time — collapse it so the next trip stays in front
        later = "\n".join([SHOPPING_WANTED_LATER, *(_render_later_item(item) for item in shopping_list.wanted_later)])
        lines.extend(["", f"<blockquote expandable>{later}</blockquote>"])

    return "\n".join(lines)


def _render_later_item(item: ShoppingItemDetails) -> str:
    if not item.is_tracked:
        return f"· {escape(item.name)}"
    # a bookmark marks a watched item, and the price with its arrow follows — this is its whole visible difference
    arrow = PRICE_TREND_ARROWS[item.price_trend]
    return f"🔖 {escape(item.name)} — {_format_hryvnia(item.current_price)} ₴ {arrow}".rstrip()


def _format_hryvnia(amount: int) -> str:
    # non-breaking thousands separator, the way hotline renders it ("39 199")
    return f"{amount:,}".replace(",", " ")


def render_price_drop_alert(announcement: PriceDropAnnouncement) -> str:
    lines = [
        PRICE_DROP_ALERT.format(
            name=escape(announcement.name),
            new_price=_format_hryvnia(announcement.new_price),
            previous_low=_format_hryvnia(announcement.previous_low),
        )
    ]
    if announcement.shop:
        rating = PRICE_DROP_SHOP_RATING.format(rating=announcement.rating) if announcement.rating else ""
        shop = PRICE_DROP_SHOP.format(shop=escape(announcement.shop), rating=rating)
        # the shop's own page (via hotline's redirect) if we have it, else the hotline product page
        lines.append(f'<a href="{escape(announcement.buy_link or announcement.hotline_url)}">{shop}</a>')
    else:
        lines.append(announcement.hotline_url)
    return "\n".join(lines)


def render_price_watch_broken(names: list[str]) -> str:
    return PRICE_WATCH_BROKEN.format(names=", ".join(escape(name) for name in names))
