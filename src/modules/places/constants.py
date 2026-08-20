from enum import StrEnum


class PlaceSetting(StrEnum):
    # the one attribute the weather-aware suggester will need later; stored now so it needs no migration then
    INDOOR = "indoor"
    OUTDOOR = "outdoor"


PLACE_NAME_MAX_LENGTH = 128
PLACE_LINK_MAX_LENGTH = 512
PLACE_ADDRESS_MAX_LENGTH = 256
PLACE_NOTE_MAX_LENGTH = 512
