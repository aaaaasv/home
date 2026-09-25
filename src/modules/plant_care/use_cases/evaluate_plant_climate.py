from datetime import datetime, timedelta

from src.common.constants import ClimateComfortTransition, ClimateDimension, ClimateStatus
from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.models import Plant
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.domain import ClimateProblem, PlantComfortChange
from src.modules.plant_care.services.room_air import RoomAir, read_air_by_room


class EvaluatePlantClimateUseCase(BaseUseCase):
    """
    Reports the plants that just crossed the line between comfortable and not, each judged by its own room.

    it speaks on an EDGE, never on a level: a heated flat is dry all winter, so a plant below its humidity floor
    would fire every single day and get the group muted. comfort is judged per plant across all its dimensions —
    a plant is comfortable only when every dimension is back in range — because the caller keeps a standing
    discomfort card per plant, deletes it on recovery, and must never repeat one that has not changed.

    a plant with no room, or whose room has no sensor covering the window, is skipped rather than judged by
    somebody else's air. that silence is the point: this bot spent a month telling the plants how the server
    shelf felt, and a plausible wrong number is worse than no number because nobody goes looking for it.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        household_calendar: HouseholdCalendar,
        alert_window_hours: int,
        temperature_hysteresis_celsius: float,
        humidity_hysteresis_percent: float,
    ):
        super().__init__(uow)
        self.household_calendar = household_calendar
        self.alert_window_hours = alert_window_hours
        self.temperature_hysteresis_celsius = temperature_hysteresis_celsius
        self.humidity_hysteresis_percent = humidity_hysteresis_percent

    async def __call__(self) -> list[PlantComfortChange]:
        measured_at = self.household_calendar.now()
        window_start = measured_at - timedelta(hours=self.alert_window_hours)

        async with self.uow as uow:
            plants = [plant for plant in await uow.plants.list_active_with_climate_range() if plant.room]
            if not plants:
                return []

            air_by_room = await read_air_by_room(
                uow, {plant.room for plant in plants}, window_start, self.alert_window_hours
            )

            changes: list[PlantComfortChange] = []
            for plant in plants:
                air = air_by_room.get(plant.room)
                if air is None:
                    continue
                change = await self._evaluate_plant(uow, plant, air, measured_at)
                if change is not None:
                    changes.append(change)
            return changes

    async def _evaluate_plant(
        self, uow: UnitOfWork, plant: Plant, air: RoomAir, measured_at: datetime
    ) -> PlantComfortChange | None:
        was_uncomfortable = False
        anything_changed = False
        problems: list[ClimateProblem] = []

        for dimension, value, low, high, margin in self._dimensions_of(plant, air):
            latest = await uow.plant_climate_alerts.retrieve_latest(plant.id, dimension)
            previous_status = ClimateStatus(latest.status) if latest is not None else ClimateStatus.OK
            new_status = self._resolve_status(value, low, high, previous_status, margin)

            if previous_status != ClimateStatus.OK:
                was_uncomfortable = True
            if new_status != ClimateStatus.OK:
                problems.append(
                    ClimateProblem(dimension=dimension, status=new_status, value=value, ideal_min=low, ideal_max=high)
                )
            if new_status != previous_status:
                anything_changed = True
                # append-only, so the newest row is this dimension's current state and a restart cannot re-alert
                await uow.plant_climate_alerts.create(
                    {
                        "plant_id": plant.id,
                        "dimension": dimension,
                        "status": new_status,
                        "value": value,
                        "notified_at": measured_at,
                    }
                )

        return self._resolve_comfort_change(plant, was_uncomfortable, anything_changed, problems)

    def _resolve_comfort_change(
        self, plant: Plant, was_uncomfortable: bool, anything_changed: bool, problems: list[ClimateProblem]
    ) -> PlantComfortChange | None:
        is_uncomfortable = bool(problems)
        if is_uncomfortable and not was_uncomfortable:
            transition = ClimateComfortTransition.BECAME_UNCOMFORTABLE
        elif was_uncomfortable and not is_uncomfortable:
            transition = ClimateComfortTransition.BECAME_COMFORTABLE
        elif is_uncomfortable and anything_changed:
            # still out of range, but on different dimensions than before — the card needs rewriting, quietly
            transition = ClimateComfortTransition.STILL_UNCOMFORTABLE
        else:
            return None
        return PlantComfortChange(plant_id=plant.id, plant_name=plant.name, transition=transition, problems=problems)

    def _dimensions_of(self, plant: Plant, air: RoomAir) -> list[tuple[ClimateDimension, float, float, float, float]]:
        dimensions = []
        if plant.ideal_temperature_min_celsius is not None and plant.ideal_temperature_max_celsius is not None:
            dimensions.append(
                (
                    ClimateDimension.TEMPERATURE,
                    air.temperature_celsius,
                    plant.ideal_temperature_min_celsius,
                    plant.ideal_temperature_max_celsius,
                    self.temperature_hysteresis_celsius,
                )
            )
        if plant.ideal_humidity_min_percent is not None and plant.ideal_humidity_max_percent is not None:
            dimensions.append(
                (
                    ClimateDimension.HUMIDITY,
                    air.relative_humidity_percent,
                    plant.ideal_humidity_min_percent,
                    plant.ideal_humidity_max_percent,
                    self.humidity_hysteresis_percent,
                )
            )
        return dimensions

    def _resolve_status(
        self, value: float, low: float, high: float, previous_status: ClimateStatus, margin: float
    ) -> ClimateStatus:
        if value < low:
            return ClimateStatus.TOO_LOW
        if value > high:
            return ClimateStatus.TOO_HIGH
        # inside the range: hold the alert until the median has climbed a margin back in, so it cannot flap on the edge
        if previous_status == ClimateStatus.TOO_LOW and value < low + margin:
            return ClimateStatus.TOO_LOW
        if previous_status == ClimateStatus.TOO_HIGH and value > high - margin:
            return ClimateStatus.TOO_HIGH
        return ClimateStatus.OK
