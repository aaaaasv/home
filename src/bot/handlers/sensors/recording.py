"""What the broker calls when a sensor speaks — the one line between the mqtt surface and the database."""
from collections.abc import Callable

from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.sensors.commands import RecordSensorReadingCommand
from src.modules.sensors.use_cases.record_sensor_reading import RecordSensorReadingUseCase


def build_sensor_recorder(uow_factory: Callable[[], UnitOfWork], household_calendar: HouseholdCalendar):
    """Hand the mqtt side one thing it can call, so it never learns what a unit of work is."""

    async def record_sensor_reading(data: RecordSensorReadingCommand) -> None:
        await RecordSensorReadingUseCase(uow=uow_factory(), household_calendar=household_calendar)(data)

    return record_sensor_reading
