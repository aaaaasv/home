from datetime import timedelta

from src.common.constants import ClimateComfortTransition, ClimateDimension, ClimateStatus
from src.common.time import current_time
from src.common.use_case import BaseUseCase
from src.infrastructure.db.models import Plant
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.domain import ClimateProblem, PlantComfortChange
from src.modules.plant_care.services.room_air import RoomAir, read_air_by_room


class RetrieveUncomfortablePlantsUseCase(BaseUseCase):
    """
    A read-only view of which plants are flagged uncomfortable right now, paired with the current median value.

    the edge job (EvaluatePlantClimateUseCase) owns the flag: when a plant crosses the line it writes the alert
    row that stays the truth until it crosses back. this reads that flag and renders it against the fresh median
    of the plant's own room, so a caller can re-surface a standing card that scrolled away or was lost — without
    re-deciding comfort or writing anything.
    """

    def __init__(self, uow: UnitOfWork, alert_window_hours: int):
        super().__init__(uow)
        self.alert_window_hours = alert_window_hours

    async def __call__(self) -> list[PlantComfortChange]:
        window_start = current_time() - timedelta(hours=self.alert_window_hours)
        async with self.uow as uow:
            plants = [plant for plant in await uow.plants.list_active_with_climate_range() if plant.room]
            if not plants:
                return []

            air_by_room = await read_air_by_room(
                uow, {plant.room for plant in plants}, window_start, self.alert_window_hours
            )

            uncomfortable: list[PlantComfortChange] = []
            for plant in plants:
                air = air_by_room.get(plant.room)
                if air is None:
                    continue
                problems: list[ClimateProblem] = []
                for dimension, value, low, high in self._dimensions_of(plant, air):
                    latest = await uow.plant_climate_alerts.retrieve_latest(plant.id, dimension)
                    if latest is None:
                        continue
                    status = ClimateStatus(latest.status)
                    if status != ClimateStatus.OK:
                        problems.append(
                            ClimateProblem(
                                dimension=dimension, status=status, value=value, ideal_min=low, ideal_max=high
                            )
                        )
                if problems:
                    uncomfortable.append(
                        PlantComfortChange(
                            plant_id=plant.id,
                            plant_name=plant.name,
                            transition=ClimateComfortTransition.STILL_UNCOMFORTABLE,
                            problems=problems,
                        )
                    )
            return uncomfortable

    def _dimensions_of(self, plant: Plant, air: RoomAir) -> list[tuple[ClimateDimension, float, float, float]]:
        dimensions = []
        if plant.ideal_temperature_min_celsius is not None and plant.ideal_temperature_max_celsius is not None:
            dimensions.append(
                (
                    ClimateDimension.TEMPERATURE,
                    air.temperature_celsius,
                    plant.ideal_temperature_min_celsius,
                    plant.ideal_temperature_max_celsius,
                )
            )
        if plant.ideal_humidity_min_percent is not None and plant.ideal_humidity_max_percent is not None:
            dimensions.append(
                (
                    ClimateDimension.HUMIDITY,
                    air.relative_humidity_percent,
                    plant.ideal_humidity_min_percent,
                    plant.ideal_humidity_max_percent,
                )
            )
        return dimensions
