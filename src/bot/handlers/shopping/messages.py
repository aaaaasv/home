"""What the shopping module says."""

from src.modules.shopping.constants import PriceTrend

PRICE_TREND_ARROWS: dict[PriceTrend, str] = {
    PriceTrend.DOWN: "↓",
    PriceTrend.UP: "↑",
    PriceTrend.FLAT: "",
}
TRACK_NEEDS_LINK = "Дай посилання на товар з hotline.ua: /track <лінк>"
# a status banner while the hotline page is fetched (~1-2s); it morphs into the result or the error
TRACK_CHECKING = "🔎 перевіряю посилання…"
TRACK_NOT_HOTLINE = "Стежити можна лише за посиланням з hotline.ua."
TRACK_UNREADABLE = "Не вдалося прочитати сторінку 😕 Перевір посилання."
SHOPPING_TRACK_BUTTON = "🔖 Стежити"
SHOPPING_TRACK_ASK_LINK = "Надішли посилання на <b>{name}</b> з hotline.ua.\n\n/cancel — скасувати"
PRICE_DROP_ALERT = "📉 <b>{name}</b> подешевшав\n{new_price} ₴ <s>{previous_low} ₴</s>"
# the shop line names who has it and how trusted they are, so a drop reads as buyable, not a no-name bait price
PRICE_DROP_SHOP = "🏬 {shop}{rating}"
PRICE_DROP_SHOP_RATING = " · рейтинг {rating}"
PRICE_WATCH_BROKEN = "⚠️ Не зчиталась ціна: {names}. Схоже, Hotline змінив верстку."

SHOPPING_LIST_TITLE = "🛒 <b>Список покупок</b>"
SHOPPING_NEEDED_NOW = "<b>Зараз</b>"
SHOPPING_WANTED_LATER = "<b>Колись</b>"
SHOPPING_LIST_EMPTY = "🛒 Список порожній. Напиши, що купити — просто текстом."
SHOPPING_ADD_NEEDS_TEXT = "Напиши, що купити — просто текстом, без команди."
SHOPPING_LATER_NEEDS_TEXT = "Напиши, що саме. Наприклад: <code>/later пилосос</code>"
SHOPPING_NAME_TOO_LONG = "Задовга назва — до 128 символів."
SHOPPING_BOUGHT_TOAST = "Купили ✅"
SHOPPING_PHOTO_NEEDS_CAPTION = "Додай до фото підпис — назву покупки."
SHOPPING_PHOTO_ASK = "Надішли фото для «{name}».\n\n/cancel — скасувати"
SHOPPING_PHOTO_EXPECTS_PHOTO = "Надішли саме фото або /cancel."
SHOPPING_PHOTO_SAVED_TOAST = "Фото додано 📷"
SHOPPING_BUY_BUTTON = "✅ Купили"
SHOPPING_PROMOTE_BUTTON = "⬆️ У «Зараз»"
SHOPPING_PHOTO_ADD_BUTTON = "📷 Фото"
SHOPPING_NOTE_ADD_BUTTON = "📝 Опис"
SHOPPING_NOTE_EDIT_BUTTON = "📝 Змінити опис"
SHOPPING_PHOTO_REPLACE_BUTTON = "📷 Замінити фото"
SHOPPING_ASK_NEW_NAME = "Надішли нову назву для «{name}».\n\n/cancel — скасувати"
SHOPPING_ASK_NOTE = (
    "Надішли опис для «{name}» — виміри, посилання, будь-що уточнювальне.\n\n"
    "«-» — прибрати опис · /cancel — скасувати"
)
SHOPPING_NOTE_TOO_LONG = "Задовгий опис — до 1024 символів."
