from datetime import date, datetime

from src.common.constants import (
    MAXIMUM_POSTPONE_DAYS,
    MINIMUM_POSTPONE_DAYS,
    POSTPONE_INTERVAL_DIVISOR,
    SKIPPABLE_TASK_TYPES,
    CareTaskType,
    ClimateComfortTransition,
    ClimateDimension,
    ClimateStatus,
    PlantPhotoReviewStatus,
)
from src.common.domain import DomainModel
from src.infrastructure.db.models import CareEvent, CareSchedule, Plant, PlantPhoto


class CareScheduleDetails(DomainModel):
    task_type: CareTaskType
    interval_days: int
    next_due_on: date
    last_performed_at: datetime | None
    days_until_due: int
    instructions: str | None = None

    @classmethod
    def from_schedule(cls, schedule: CareSchedule, today: date) -> "CareScheduleDetails":
        next_due_on = seasonal_next_due(
            schedule.next_due_on, today, schedule.season_start_month, schedule.season_end_month
        )
        return cls(
            task_type=CareTaskType(schedule.task_type),
            interval_days=schedule.interval_days,
            next_due_on=next_due_on,
            last_performed_at=schedule.last_performed_at,
            days_until_due=(next_due_on - today).days,
            instructions=schedule.instructions,
        )

    @property
    def is_due(self) -> bool:
        return self.days_until_due <= 0

    @property
    def overdue_days(self) -> int:
        return max(-self.days_until_due, 0)


class CareEventDetails(DomainModel):
    task_type: CareTaskType
    performed_at: datetime
    performed_by_display_name: str
    note: str | None

    @classmethod
    def from_event(cls, event: CareEvent) -> "CareEventDetails":
        return cls(
            task_type=CareTaskType(event.task_type),
            performed_at=event.performed_at,
            performed_by_display_name=event.performed_by_display_name,
            note=event.note,
        )


class PlantPhotoDetails(DomainModel):
    telegram_file_id: str
    caption: str | None
    taken_at: datetime

    @classmethod
    def from_photo(cls, photo: PlantPhoto) -> "PlantPhotoDetails":
        return cls(telegram_file_id=photo.telegram_file_id, caption=photo.caption, taken_at=photo.taken_at)


class PlantSummary(DomainModel):
    id: int
    name: str
    location: str | None
    schedules: list[CareScheduleDetails]

    @property
    def most_urgent_schedule(self) -> CareScheduleDetails | None:
        if not self.schedules:
            return None
        return min(self.schedules, key=lambda schedule: schedule.next_due_on)


class PlantCard(DomainModel):
    id: int
    name: str
    species: str | None
    location: str | None
    notes: str | None
    ideal_temperature_min_celsius: float | None = None
    ideal_temperature_max_celsius: float | None = None
    ideal_humidity_min_percent: float | None = None
    ideal_humidity_max_percent: float | None = None
    created_at: datetime
    schedules: list[CareScheduleDetails]
    recent_events: list[CareEventDetails]
    latest_photo: PlantPhotoDetails | None
    photo_count: int

    @classmethod
    def from_models(
        cls,
        plant: Plant,
        schedules: list[CareSchedule],
        recent_events: list[CareEvent],
        photos: list[PlantPhoto],
        today: date,
    ) -> "PlantCard":
        return cls(
            id=plant.id,
            name=plant.name,
            species=plant.species,
            location=plant.location,
            notes=plant.notes,
            ideal_temperature_min_celsius=plant.ideal_temperature_min_celsius,
            ideal_temperature_max_celsius=plant.ideal_temperature_max_celsius,
            ideal_humidity_min_percent=plant.ideal_humidity_min_percent,
            ideal_humidity_max_percent=plant.ideal_humidity_max_percent,
            created_at=plant.created_at,
            schedules=[CareScheduleDetails.from_schedule(schedule, today) for schedule in schedules],
            recent_events=[CareEventDetails.from_event(event) for event in recent_events],
            latest_photo=PlantPhotoDetails.from_photo(photos[-1]) if photos else None,
            photo_count=len(photos),
        )


class ClimateProblem(DomainModel):
    """One dimension a plant is currently outside its ideal range on — a line on its discomfort card"""

    dimension: ClimateDimension
    status: ClimateStatus
    value: float
    ideal_min: float
    ideal_max: float


class PlantComfortChange(DomainModel):
    """
    A plant crossed the line between comfortable and not — the only thing worth a message.

    problems carry the plant's whole current discomfort (both dimensions if both are out), so one card speaks for
    the plant rather than one line per dimension. it is empty exactly when the transition is BECAME_COMFORTABLE.
    """

    plant_id: int
    plant_name: str
    transition: ClimateComfortTransition
    problems: list[ClimateProblem]


def is_in_growing_season(day: date, season_start_month: int | None, season_end_month: int | None) -> bool:
    # a null window is year-round care (watering); a range gates a seasonal task (fertilizing) to those months
    if season_start_month is None or season_end_month is None:
        return True
    return season_start_month <= day.month <= season_end_month


def seasonal_next_due(
    next_due_on: date, today: date, season_start_month: int | None, season_end_month: int | None
) -> date:
    """
    The real next date a seasonal task should be done, folding the growing-season window over the stored date.

    off-season it is the coming season's first day, so a task that fell due last autumn waits silently for spring
    instead of piling up months of "overdue"; in-season a stale off-season due date is pulled up to the season
    start, so the first spring reminder reads "due today", not "overdue 180 days".
    """
    if season_start_month is None or season_end_month is None:
        return next_due_on
    if is_in_growing_season(today, season_start_month, season_end_month):
        return max(next_due_on, date(today.year, season_start_month, 1))
    next_season_year = today.year if today.month < season_start_month else today.year + 1
    return date(next_season_year, season_start_month, 1)


def calculate_postpone_days(interval_days: int) -> int:
    return min(max(interval_days // POSTPONE_INTERVAL_DIVISOR, MINIMUM_POSTPONE_DAYS), MAXIMUM_POSTPONE_DAYS)


def calculate_defer_days(task_type: CareTaskType, interval_days: int) -> int:
    # a skippable task defers a whole cycle at once; the rest get a short nudge, a third of their interval
    if task_type in SKIPPABLE_TASK_TYPES:
        return interval_days
    return calculate_postpone_days(interval_days)


class DueCareTask(DomainModel):
    plant_id: int
    plant_name: str
    task_type: CareTaskType
    interval_days: int
    overdue_days: int
    photo_file_id: str | None = None
    instructions: str | None = None

    @property
    def is_skippable(self) -> bool:
        return self.task_type in SKIPPABLE_TASK_TYPES

    @property
    def postpone_days(self) -> int:
        return calculate_defer_days(self.task_type, self.interval_days)


class CareDigest(DomainModel):
    today: date
    tasks: list[DueCareTask]

    @classmethod
    def from_due_schedules(
        cls,
        today: date,
        due_schedules: list[tuple[CareSchedule, Plant]],
        photo_file_ids: dict[int, str] | None = None,
    ) -> "CareDigest":
        photo_file_ids = photo_file_ids or {}
        return cls(
            today=today,
            tasks=[
                DueCareTask(
                    plant_id=plant.id,
                    plant_name=plant.name,
                    task_type=CareTaskType(schedule.task_type),
                    interval_days=schedule.interval_days,
                    overdue_days=(
                        today
                        - seasonal_next_due(
                            schedule.next_due_on, today, schedule.season_start_month, schedule.season_end_month
                        )
                    ).days,
                    photo_file_id=photo_file_ids.get(plant.id),
                    instructions=schedule.instructions,
                )
                for schedule, plant in due_schedules
                if is_in_growing_season(today, schedule.season_start_month, schedule.season_end_month)
            ],
        )


class PostponedCareTask(DomainModel):
    plant_id: int
    plant_name: str
    task_type: CareTaskType
    next_due_on: date


class CareRecord(DomainModel):
    plant_id: int
    plant_name: str
    task_type: CareTaskType
    performed_by_display_name: str
    next_due_on: date


class CareHistoryEntry(DomainModel):
    plant_name: str
    task_type: CareTaskType
    performed_at: datetime
    performed_by_display_name: str


class PhotoReviewSchedule(DomainModel):
    task_type: CareTaskType
    interval_days: int
    days_since_last_performed: int | None


class PlantPhotoReviewContext(DomainModel):
    """Everything the bot knows about a plant at the moment its photo was taken"""

    plant_name: str
    species: str | None
    location: str | None
    ideal_temperature_min_celsius: float | None
    ideal_temperature_max_celsius: float | None
    ideal_humidity_min_percent: float | None
    ideal_humidity_max_percent: float | None
    room_temperature_celsius: float | None
    room_humidity_percent: float | None
    schedules: list[PhotoReviewSchedule]
    current_photo_path: str
    previous_photo_path: str | None
    days_since_previous_photo: int | None


class PlantPhotoReview(DomainModel):
    status: PlantPhotoReviewStatus
    summary: str
    change: str | None
    action: str | None
