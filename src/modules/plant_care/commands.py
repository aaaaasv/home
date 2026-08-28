from datetime import date, datetime

from pydantic import BaseModel, Field

from src.common.constants import (
    CARE_INSTRUCTIONS_MAX_LENGTH,
    MAXIMUM_CARE_INTERVAL_DAYS,
    MAXIMUM_PLANT_HUMIDITY_PERCENT,
    MAXIMUM_PLANT_TEMPERATURE_CELSIUS,
    MINIMUM_CARE_INTERVAL_DAYS,
    MINIMUM_PLANT_HUMIDITY_PERCENT,
    MINIMUM_PLANT_TEMPERATURE_CELSIUS,
    PLANT_LOCATION_MAX_LENGTH,
    PLANT_NAME_MAX_LENGTH,
    PLANT_NOTES_MAX_LENGTH,
    PLANT_SPECIES_MAX_LENGTH,
    CareTaskType,
    PlantPhotoFrame,
)


class TelegramPhoto(BaseModel):
    file_id: str
    file_unique_id: str
    caption: str | None = None


class CreatePlantCommand(BaseModel):
    name: str = Field(min_length=1, max_length=PLANT_NAME_MAX_LENGTH)
    species: str | None = Field(default=None, max_length=PLANT_SPECIES_MAX_LENGTH)
    location: str | None = Field(default=None, max_length=PLANT_LOCATION_MAX_LENGTH)
    notes: str | None = Field(default=None, max_length=PLANT_NOTES_MAX_LENGTH)
    photo: TelegramPhoto | None = None
    watering_interval_days: int = Field(ge=MINIMUM_CARE_INTERVAL_DAYS, le=MAXIMUM_CARE_INTERVAL_DAYS)
    last_watered_on: date | None = None


class UpdatePlantCommand(BaseModel):
    """Only the fields explicitly passed are written, so passing None clears a field"""

    plant_id: int
    name: str | None = Field(default=None, min_length=1, max_length=PLANT_NAME_MAX_LENGTH)
    species: str | None = Field(default=None, max_length=PLANT_SPECIES_MAX_LENGTH)
    location: str | None = Field(default=None, max_length=PLANT_LOCATION_MAX_LENGTH)
    notes: str | None = Field(default=None, max_length=PLANT_NOTES_MAX_LENGTH)
    ideal_temperature_min_celsius: float | None = Field(
        default=None, ge=MINIMUM_PLANT_TEMPERATURE_CELSIUS, le=MAXIMUM_PLANT_TEMPERATURE_CELSIUS
    )
    ideal_temperature_max_celsius: float | None = Field(
        default=None, ge=MINIMUM_PLANT_TEMPERATURE_CELSIUS, le=MAXIMUM_PLANT_TEMPERATURE_CELSIUS
    )
    ideal_humidity_min_percent: float | None = Field(
        default=None, ge=MINIMUM_PLANT_HUMIDITY_PERCENT, le=MAXIMUM_PLANT_HUMIDITY_PERCENT
    )
    ideal_humidity_max_percent: float | None = Field(
        default=None, ge=MINIMUM_PLANT_HUMIDITY_PERCENT, le=MAXIMUM_PLANT_HUMIDITY_PERCENT
    )

    def build_changes(self) -> dict[str, str | float | None]:
        return self.model_dump(exclude_unset=True, exclude={"plant_id"})


class SetCareScheduleCommand(BaseModel):
    plant_id: int
    task_type: CareTaskType
    interval_days: int = Field(ge=MINIMUM_CARE_INTERVAL_DAYS, le=MAXIMUM_CARE_INTERVAL_DAYS)


class RemoveCareScheduleCommand(BaseModel):
    plant_id: int
    task_type: CareTaskType


class SetCareInstructionsCommand(BaseModel):
    plant_id: int
    task_type: CareTaskType
    instructions: str | None = Field(default=None, max_length=CARE_INSTRUCTIONS_MAX_LENGTH)


class RecordCareEventCommand(BaseModel):
    plant_id: int
    task_type: CareTaskType
    performed_at: datetime
    note: str | None = None
    force: bool = False


class UndoCareEventCommand(BaseModel):
    plant_id: int
    task_type: CareTaskType


class PostponeCareTaskCommand(BaseModel):
    plant_id: int
    task_type: CareTaskType
    postponed_at: datetime


class AddPlantPhotoCommand(BaseModel):
    plant_id: int
    photo: TelegramPhoto
    taken_at: datetime
    frame: PlantPhotoFrame = PlantPhotoFrame.OVERVIEW


class ArchivePlantCommand(BaseModel):
    plant_id: int


class RestorePlantCommand(BaseModel):
    plant_id: int
