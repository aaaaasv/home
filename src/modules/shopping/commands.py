from pydantic import BaseModel, Field

from src.modules.shopping.constants import (
    HOTLINE_URL_MAX_LENGTH,
    SHOPPING_ITEM_NAME_MAX_LENGTH,
    SHOPPING_ITEM_NOTE_MAX_LENGTH,
    ShoppingHorizon,
)


class AddShoppingItemCommand(BaseModel):
    name: str = Field(min_length=1, max_length=SHOPPING_ITEM_NAME_MAX_LENGTH)
    horizon: ShoppingHorizon = ShoppingHorizon.NOW
    photo_telegram_file_id: str | None = None


class TrackShoppingItemCommand(BaseModel):
    hotline_url: str = Field(min_length=1, max_length=HOTLINE_URL_MAX_LENGTH)


class TrackExistingItemCommand(BaseModel):
    item_id: int
    hotline_url: str = Field(min_length=1, max_length=HOTLINE_URL_MAX_LENGTH)


class BuyShoppingItemCommand(BaseModel):
    item_id: int


class RenameShoppingItemCommand(BaseModel):
    item_id: int
    name: str = Field(min_length=1, max_length=SHOPPING_ITEM_NAME_MAX_LENGTH)


class SetShoppingItemPhotoCommand(BaseModel):
    item_id: int
    photo_telegram_file_id: str = Field(min_length=1)


class PromoteShoppingItemCommand(BaseModel):
    item_id: int


class RemoveShoppingItemCommand(BaseModel):
    item_id: int


class SetShoppingItemNoteCommand(BaseModel):
    item_id: int
    # an empty note clears it — the card should be able to go back to just a name
    note: str = Field(default="", max_length=SHOPPING_ITEM_NOTE_MAX_LENGTH)
