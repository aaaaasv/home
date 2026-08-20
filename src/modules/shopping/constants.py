from enum import StrEnum


class ShoppingHorizon(StrEnum):
    NOW = "now"
    LATER = "later"


class PriceTrend(StrEnum):
    DOWN = "down"
    UP = "up"
    FLAT = "flat"


SHOPPING_ITEM_NAME_MAX_LENGTH = 128
# room for measurements, a link and a sentence of context — the things a bare name cannot hold
SHOPPING_ITEM_NOTE_MAX_LENGTH = 1024
HOTLINE_URL_MAX_LENGTH = 512
# hotline's h1 is long ("Смартфон Apple iPhone 17 256GB Black (MG6J4)"); keep the shopping line readable
TRACKED_ITEM_NAME_MAX_LENGTH = 64
