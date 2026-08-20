from pydantic import BaseModel, Field

from src.modules.places.constants import PLACE_LINK_MAX_LENGTH, PLACE_NAME_MAX_LENGTH


class AddPlaceCommand(BaseModel):
    name: str = Field(min_length=1, max_length=PLACE_NAME_MAX_LENGTH)
    link: str | None = Field(default=None, max_length=PLACE_LINK_MAX_LENGTH)


class RenamePlaceCommand(BaseModel):
    place_id: int
    name: str = Field(min_length=1, max_length=PLACE_NAME_MAX_LENGTH)


class MarkPlaceVisitedCommand(BaseModel):
    place_id: int


class RemovePlaceCommand(BaseModel):
    place_id: int
