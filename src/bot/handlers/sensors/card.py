from collections.abc import Callable

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.bot.handlers.sensors.formatting import render_climate_card
from src.common.config import Settings
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.use_cases.list_plants import ListPlantsUseCase
from src.modules.sensors.use_cases.measure_climate_trend import MeasureClimateTrendUseCase
from src.modules.sensors.use_cases.retrieve_climate_snapshot import RetrieveClimateSnapshotUseCase

router = Router(name="climate_card")


# a pull, never a push: rule 1 — the temperature at home is not news, and a card that spoke every morning
# about nothing would get the topic muted, taking the alerts that matter with it
@router.message(Command("climate"))
async def show_climate(
    message: Message,
    uow_factory: Callable[[], UnitOfWork],
    settings: Settings,
    household_calendar: HouseholdCalendar,
) -> None:
    """The whole flat at a glance — every room, every pot with a probe in it, and which way it is moving."""
    snapshot = await RetrieveClimateSnapshotUseCase(
        uow=uow_factory(), household_calendar=household_calendar, rooms=settings.room_by_sensor
    )(soil_sensors=set(settings.plant_by_soil_sensor))
    trend = await MeasureClimateTrendUseCase(uow=uow_factory(), household_calendar=household_calendar)(
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

    await message.answer(render_climate_card(snapshot, trend, pot_labels, household_calendar))
