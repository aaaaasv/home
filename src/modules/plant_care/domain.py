from datetime import date, datetime

from src.common.constants import (
    MAXIMUM_POSTPONE_DAYS,
    MINIMUM_POSTPONE_DAYS,
    MONTHS_IN_YEAR,
    POSTPONE_INTERVAL_DIVISOR,
    SKIPPABLE_TASK_TYPES,
    CareTaskType,
    ClimateComfortTransition,
    ClimateDimension,
    ClimateStatus,
    PlantPhotoFrame,
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
        next_due_on = active_next_due(schedule.next_due_on, today, schedule.month_interval_overrides)
        month_interval = resolve_month_interval(today, schedule.interval_days, schedule.month_interval_overrides)
        return cls(
            task_type=CareTaskType(schedule.task_type),
            # a silent month has no interval of its own, so the card falls back to the schedule's own pace
            interval_days=month_interval if month_interval is not None else schedule.interval_days,
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
    def from_event(cls, event: CareEvent, current_names: dict[int, str] | None = None) -> "CareEventDetails":
        """Current_names re-credits the event to whatever its author goes by now, leaving the record untouched."""
        names = current_names or {}
        return cls(
            task_type=CareTaskType(event.task_type),
            performed_at=event.performed_at,
            performed_by_display_name=names.get(event.performed_by_telegram_user_id, event.performed_by_display_name),
            note=event.note,
        )


class PlantPhotoDetails(DomainModel):
    id: int
    telegram_file_id: str
    caption: str | None
    taken_at: datetime
    frame: PlantPhotoFrame

    @classmethod
    def from_photo(cls, photo: PlantPhoto) -> "PlantPhotoDetails":
        return cls(
            id=photo.id,
            telegram_file_id=photo.telegram_file_id,
            caption=photo.caption,
            taken_at=photo.taken_at,
            frame=PlantPhotoFrame(photo.frame),
        )


def find_cover_photo(photos: list[PlantPhotoDetails]) -> PlantPhotoDetails | None:
    """
    The newest general frame, which stands for the plant on its card and its sheet.

    an album saves its close-ups after the general frame, so the newest photo of all is a single leaf.
    """
    return next((photo for photo in reversed(photos) if photo.frame == PlantPhotoFrame.OVERVIEW), None)


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
    cover_photo: PlantPhotoDetails | None
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
            cover_photo=find_cover_photo([PlantPhotoDetails.from_photo(photo) for photo in photos]),
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


def resolve_month_interval(
    day: date, interval_days: int, month_interval_overrides: dict[str, int | None] | None
) -> int | None:
    """
    The interval in force on a day, or None when the task is not done at all in that month.

    Json object keys are strings, so a month is looked up as one. A month with no entry falls back to the
    schedule's own interval; a month whose entry is null is a deliberate "never in this month", which is how a
    plant that sleeps rather than merely slows is written down.
    """
    if not month_interval_overrides:
        return interval_days
    return month_interval_overrides.get(str(day.month), interval_days)


def is_care_done_in_month(day: date, month_interval_overrides: dict[str, int | None] | None) -> bool:
    if not month_interval_overrides:
        return True
    month = str(day.month)
    return month not in month_interval_overrides or month_interval_overrides[month] is not None


def find_active_stretch_start(day: date, month_interval_overrides: dict[str, int | None] | None) -> date:
    """
    The first day of the unbroken run of active months this day sits in.

    With no silent month anywhere the walk runs its full length and lands a year back, which is harmless: the
    only caller compares it against a stored due date and keeps the later of the two.
    """
    year, month = day.year, day.month
    for _ in range(MONTHS_IN_YEAR):
        earlier_year, earlier_month = (year - 1, MONTHS_IN_YEAR) if month == 1 else (year, month - 1)
        if not is_care_done_in_month(date(earlier_year, earlier_month, 1), month_interval_overrides):
            break
        year, month = earlier_year, earlier_month
    return date(year, month, 1)


def find_next_active_month_start(day: date, month_interval_overrides: dict[str, int | None] | None) -> date:
    """The first day of the next month the task is done in."""
    year, month = day.year, day.month
    for _ in range(MONTHS_IN_YEAR):
        year, month = (year + 1, 1) if month == MONTHS_IN_YEAR else (year, month + 1)
        if is_care_done_in_month(date(year, month, 1), month_interval_overrides):
            return date(year, month, 1)
    # every month silenced means the task is never done; the schedule is then its own answer
    return date(day.year, day.month, 1)


def active_next_due(next_due_on: date, today: date, month_interval_overrides: dict[str, int | None] | None) -> date:
    """
    The real next date a task should be done, folding months of silence over the stored date.

    in a silent month it is the first day of the next month the task happens in, so a task that fell due last
    autumn waits quietly for spring instead of piling up months of "overdue"; in an active month a due date left
    behind in a silent stretch is pulled up to the day that stretch ended, so the first reminder after it reads
    "due today", not "overdue 180 days".
    """
    if not month_interval_overrides:
        return next_due_on
    if is_care_done_in_month(today, month_interval_overrides):
        return max(next_due_on, find_active_stretch_start(today, month_interval_overrides))
    return find_next_active_month_start(today, month_interval_overrides)


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
                    interval_days=resolve_month_interval(
                        today, schedule.interval_days, schedule.month_interval_overrides
                    )
                    or schedule.interval_days,
                    overdue_days=(
                        today - active_next_due(schedule.next_due_on, today, schedule.month_interval_overrides)
                    ).days,
                    photo_file_id=photo_file_ids.get(plant.id),
                    instructions=schedule.instructions,
                )
                for schedule, plant in due_schedules
                if is_care_done_in_month(today, schedule.month_interval_overrides)
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


class ClimateInterval(DomainModel):
    """
    What the air did between two photos, folded from the daily summaries.

    the reading at the moment a photo is taken says almost nothing about why a leaf browned over six weeks.
    the span, the middle of it, and how many of those days sat below what the plant wants — those do.
    """

    days_recorded: int
    minimum_temperature_celsius: float
    maximum_temperature_celsius: float
    average_temperature_celsius: float
    minimum_humidity_percent: float
    maximum_humidity_percent: float
    average_humidity_percent: float
    days_below_ideal_humidity: int | None


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
    current_photo_taken_on: date
    previous_photo_path: str | None
    previous_photo_taken_on: date | None
    days_since_previous_photo: int | None
    climate_between_photos: ClimateInterval | None = None


class PlantPhotoReview(DomainModel):
    status: PlantPhotoReviewStatus
    summary: str
    change: str | None
    action: str | None


class CarerTally(DomainModel):
    name: str
    count: int


def plant_age_days(plant, today: date) -> int:
    """How long the plant has been in the house — counted to the day it ended, if it has."""
    return max(((plant.archived_on or today) - plant.created_at.date()).days, 0)


class PlantLink(DomainModel):
    """Another plant this one points at — enough to name it and reach its sheet, nothing more."""

    id: int
    name: str
    slug: str | None

    @property
    def reference(self) -> str:
        return self.slug or str(self.id)

    @classmethod
    def from_plant(cls, plant) -> "PlantLink":
        return cls(id=plant.id, name=plant.name, slug=plant.slug)


class DrawerEntry(DomainModel):
    """One folder in the card catalogue — enough to recognise a plant without opening its sheet."""

    id: int
    slug: str | None
    name: str
    species: str | None
    cover_photo_id: int | None
    age_days: int
    days_until_watering: int | None
    is_archived: bool

    @property
    def reference(self) -> str:
        return self.slug or str(self.id)

    @classmethod
    def from_models(cls, plant, watering, cover_photo_id, today) -> "DrawerEntry":
        return cls(
            id=plant.id,
            slug=plant.slug,
            name=plant.name,
            species=plant.species,
            cover_photo_id=cover_photo_id,
            age_days=plant_age_days(plant, today),
            # an archived plant keeps its schedules as a record of how it was kept, but nothing is due for it
            days_until_watering=(
                None if plant.is_archived else (watering.next_due_on - today).days if watering else None
            ),
            is_archived=plant.is_archived,
        )


class ClimatePoint(DomainModel):
    hour: str
    temperature_celsius: float
    relative_humidity_percent: float


class PlantIdentification(DomainModel):
    """
    What a photo alone suggests about a plant nobody has catalogued yet.

    every field is optional and nothing is ever saved from it unaided: a guess about a species is a guess, and
    watering the wrong plant on the wrong rhythm is how one gets killed. the family confirms before it counts.
    """

    common_name: str | None
    species: str | None
    watering_interval_days: int | None
    care_notes: str | None


class PlantSheet(DomainModel):
    """One plant as a specimen sheet: what it is, where it came from, and how it has actually been kept."""

    id: int
    slug: str | None
    name: str
    species: str | None
    location: str | None
    notes: str | None
    provenance: str | None
    native_range: str | None
    substrate: str | None
    toxicity: str | None
    created_at: datetime
    age_days: int
    is_archived: bool
    archived_on: date | None
    propagated_from: PlantLink | None
    offspring: list[PlantLink]
    ideal_temperature_min_celsius: float | None
    ideal_temperature_max_celsius: float | None
    ideal_humidity_min_percent: float | None
    ideal_humidity_max_percent: float | None
    current_temperature_celsius: float | None
    current_humidity_percent: float | None
    schedules: list[CareScheduleDetails]
    recent_events: list[CareEventDetails]
    photos: list[PlantPhotoDetails]
    carers: list[CarerTally]
    watering_gaps_days: list[float]
    climate: list[ClimatePoint]

    @property
    def watering(self) -> CareScheduleDetails | None:
        return next((s for s in self.schedules if s.task_type == CareTaskType.WATERING), None)

    @property
    def humidity_is_low(self) -> bool:
        floor, now = self.ideal_humidity_min_percent, self.current_humidity_percent
        return floor is not None and now is not None and now < floor

    @classmethod
    def from_models(
        cls,
        plant,
        schedules,
        recent_events,
        photos,
        carers,
        waterings,
        climate,
        latest_climate,
        today,
        current_names,
        parent=None,
        offspring=(),
    ):
        gaps = [round((later - earlier).total_seconds() / 86400, 1) for earlier, later in zip(waterings, waterings[1:])]
        return cls(
            id=plant.id,
            slug=plant.slug,
            name=plant.name,
            species=plant.species,
            location=plant.location,
            notes=plant.notes,
            provenance=plant.provenance,
            native_range=plant.native_range,
            substrate=plant.substrate,
            toxicity=plant.toxicity,
            created_at=plant.created_at,
            age_days=plant_age_days(plant, today),
            is_archived=plant.is_archived,
            archived_on=plant.archived_on,
            propagated_from=PlantLink.from_plant(parent) if parent else None,
            offspring=[PlantLink.from_plant(child) for child in offspring],
            ideal_temperature_min_celsius=plant.ideal_temperature_min_celsius,
            ideal_temperature_max_celsius=plant.ideal_temperature_max_celsius,
            ideal_humidity_min_percent=plant.ideal_humidity_min_percent,
            ideal_humidity_max_percent=plant.ideal_humidity_max_percent,
            current_temperature_celsius=latest_climate.temperature_celsius if latest_climate else None,
            current_humidity_percent=latest_climate.relative_humidity_percent if latest_climate else None,
            schedules=[CareScheduleDetails.from_schedule(s, today) for s in schedules],
            recent_events=[CareEventDetails.from_event(e, current_names) for e in recent_events],
            photos=[PlantPhotoDetails.from_photo(p) for p in photos],
            carers=[CarerTally(name=current_names.get(user_id, name), count=count) for user_id, name, count in carers],
            watering_gaps_days=gaps,
            climate=[
                ClimatePoint(hour=hour, temperature_celsius=t, relative_humidity_percent=h) for hour, t, h in climate
            ],
        )
