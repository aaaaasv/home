from collections.abc import Callable
from dataclasses import dataclass

from src.common.config import Settings
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.use_cases.list_plants import ListPlantsUseCase
from src.modules.sensors.domain import ClimateSnapshot, ClimateTrend, TemperatureSpan
from src.modules.sensors.use_cases.measure_climate_trend import MeasureClimateTrendUseCase
from src.modules.sensors.use_cases.measure_temperature_span import MeasureTemperatureSpanUseCase
from src.modules.sensors.use_cases.retrieve_climate_snapshot import RetrieveClimateSnapshotUseCase


@dataclass
class ClimateCardContents:
    """Everything the climate card says, gathered once so that posting it and refreshing it read the same."""

    snapshot: ClimateSnapshot
    trend: ClimateTrend
    temperature_spans: dict[str, TemperatureSpan]
    pot_labels: dict[str, str]
    plant_count: int


async def gather_climate_card_contents(
    uow_factory: Callable[[], UnitOfWork], settings: Settings, household_calendar: HouseholdCalendar
) -> ClimateCardContents:
    snapshot = await RetrieveClimateSnapshotUseCase(
        uow=uow_factory(), household_calendar=household_calendar, rooms=settings.room_by_sensor
    )(soil_sensors=set(settings.plant_by_soil_sensor))
    trend = await MeasureClimateTrendUseCase(uow=uow_factory(), household_calendar=household_calendar)(
        sensors=set(settings.room_by_sensor)
    )
    temperature_spans = await MeasureTemperatureSpanUseCase(uow=uow_factory(), household_calendar=household_calendar)(
        sensors=set(settings.room_by_sensor)
    )
    plants = await ListPlantsUseCase(uow=uow_factory(), household_calendar=household_calendar)()
    # a probe is named by the plant it stands in — its own identifier means nothing to anyone reading
    pot_labels = {
        sensor: plant.name
        for sensor, plant_id in settings.plant_by_soil_sensor.items()
        for plant in plants
        if plant.id == plant_id
    }
    return ClimateCardContents(
        snapshot=snapshot,
        trend=trend,
        temperature_spans=temperature_spans,
        pot_labels=pot_labels,
        plant_count=len(plants),
    )
