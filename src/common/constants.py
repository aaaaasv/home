from enum import StrEnum


class ErrorCode(StrEnum):
    NOT_FOUND = "NOT_FOUND"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    CONFLICT = "CONFLICT"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RECENT_CARE_EXISTS = "RECENT_CARE_EXISTS"


class CareTaskType(StrEnum):
    WATERING = "watering"
    FERTILIZING = "fertilizing"
    # leaching the pot with plain water to wash out fertilizer salts — its own reminder, not a step inside feeding
    FLUSH = "flush"
    REPOTTING = "repotting"
    ROTATING = "rotating"
    # a photo is scheduled like care, but it is completed by uploading a photo instead of tapping "done"
    PHOTO = "photo"


# missing one of these hurts nothing, unlike a missed watering, so their reminder offers a full-cycle skip
# (ask again next interval) rather than the short nudge that watering gets
SKIPPABLE_TASK_TYPES = frozenset({CareTaskType.FERTILIZING, CareTaskType.FLUSH, CareTaskType.PHOTO})


class PlantPhotoReviewStatus(StrEnum):
    OK = "ok"
    WATCH = "watch"
    PROBLEM = "problem"


class PlantField(StrEnum):
    NAME = "name"
    SPECIES = "species"
    LOCATION = "location"
    NOTES = "notes"
    TEMPERATURE_RANGE = "temperature_range"
    HUMIDITY_RANGE = "humidity_range"


class ClimateDimension(StrEnum):
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"


class ClimateStatus(StrEnum):
    OK = "ok"
    TOO_LOW = "too_low"
    TOO_HIGH = "too_high"


class ClimateComfortTransition(StrEnum):
    """The only three plant-level events worth a message — anything else is no change, so the bot stays quiet"""

    BECAME_UNCOMFORTABLE = "became_uncomfortable"
    STILL_UNCOMFORTABLE = "still_uncomfortable"
    BECAME_COMFORTABLE = "became_comfortable"


# telegram allows 1024 characters in a photo caption against 4096 in a plain message
TELEGRAM_CAPTION_MAX_LENGTH = 1024

PLANT_NAME_MAX_LENGTH = 64
PLANT_SPECIES_MAX_LENGTH = 128
PLANT_LOCATION_MAX_LENGTH = 128
PLANT_NOTES_MAX_LENGTH = 512

# the two edit fields that carry a numeric range ("21-29"), not free text — parsed, not length-capped
PLANT_CLIMATE_FIELDS = frozenset({PlantField.TEMPERATURE_RANGE, PlantField.HUMIDITY_RANGE})

PLANT_FIELD_MAX_LENGTHS: dict[PlantField, int] = {
    PlantField.NAME: PLANT_NAME_MAX_LENGTH,
    PlantField.SPECIES: PLANT_SPECIES_MAX_LENGTH,
    PlantField.LOCATION: PLANT_LOCATION_MAX_LENGTH,
    PlantField.NOTES: PLANT_NOTES_MAX_LENGTH,
}

MINIMUM_PLANT_TEMPERATURE_CELSIUS = 0.0
MAXIMUM_PLANT_TEMPERATURE_CELSIUS = 45.0
MINIMUM_PLANT_HUMIDITY_PERCENT = 0.0
MAXIMUM_PLANT_HUMIDITY_PERCENT = 100.0

# each range edit field maps to the two plant columns it writes and the bounds its input must fall inside
CLIMATE_FIELD_COLUMNS: dict[PlantField, tuple[str, str]] = {
    PlantField.TEMPERATURE_RANGE: ("ideal_temperature_min_celsius", "ideal_temperature_max_celsius"),
    PlantField.HUMIDITY_RANGE: ("ideal_humidity_min_percent", "ideal_humidity_max_percent"),
}
CLIMATE_FIELD_BOUNDS: dict[PlantField, tuple[float, float]] = {
    PlantField.TEMPERATURE_RANGE: (MINIMUM_PLANT_TEMPERATURE_CELSIUS, MAXIMUM_PLANT_TEMPERATURE_CELSIUS),
    PlantField.HUMIDITY_RANGE: (MINIMUM_PLANT_HUMIDITY_PERCENT, MAXIMUM_PLANT_HUMIDITY_PERCENT),
}

# a month is short enough to catch a problem early and long enough that the photo shows a visible difference
DEFAULT_PHOTO_INTERVAL_DAYS = 30

# postponing must stay well short of the cycle, or it stops being "later" and becomes "forgotten";
# the cap keeps a two-year repotting cycle from proposing a delay measured in months
POSTPONE_INTERVAL_DIVISOR = 3
MINIMUM_POSTPONE_DAYS = 1
MAXIMUM_POSTPONE_DAYS = 14

MINIMUM_CARE_INTERVAL_DAYS = 1
# repotting runs on a two-to-three year cycle, so a yearly cap would exclude it
MAXIMUM_CARE_INTERVAL_DAYS = 1095

# a per-task how-to shown as an expandable block on the digest card; capped so it fits a photo caption (1024 total)
CARE_INSTRUCTIONS_MAX_LENGTH = 600

CARE_HISTORY_PAGE_SIZE = 15
PLANT_CARD_HISTORY_SIZE = 5
