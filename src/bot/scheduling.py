"""What a module needs to schedule its own work, and the shape its scheduling entry point takes."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.bot.handlers.power.conservation_board import ConservationBoard
from src.bot.handlers.power.outage_schedule_board import OutageScheduleBoard
from src.bot.handlers.weather.board import WeatherDigestBoard
from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.bot.services.posted_message_tracker import PostedMessageTracker
from src.common.config import Settings
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork
from src.modules.air_conditioner.services.air_conditioner import AirConditioner
from src.modules.plant_care.services.room_climate_sensor import RoomClimateSensor
from src.modules.power.services.ecoflow_station import EcoFlowStation
from src.modules.power.services.outage_schedule_provider import OutageScheduleProvider
from src.modules.presence.services.presence_source import PresenceSource
from src.modules.shopping.services.price_source import PriceSource
from src.modules.system_health.services.pi_health_sensor import PiHealthSensor
from src.modules.transit.services.route_shape_catalog import RouteShapeCatalog


@dataclass(frozen=True)
class SchedulerContext:
    """
    Everything the composition root has built, offered to each module's scheduling entry point.

    a collaborator is None when its module is switched off or its topic never resolved, so a module reads the
    settings flag and the collaborators it needs and simply registers nothing when they are missing.
    """

    bot: Bot
    settings: Settings
    household_calendar: HouseholdCalendar
    care_topic: ForumTopicRegistry
    shopping_topic: ForumTopicRegistry
    chores_topic: ForumTopicRegistry
    room_climate_sensor: RoomClimateSensor
    price_source: PriceSource
    uow_factory: Callable[[], UnitOfWork] = UnitOfWork
    weather_topic: ForumTopicRegistry | None = None
    weather_digest_board: WeatherDigestBoard | None = None
    air_conditioner: AirConditioner | None = None
    tech_topic: ForumTopicRegistry | None = None
    pi_health_sensor: PiHealthSensor | None = None
    presence_source: PresenceSource | None = None
    ecoflow_station: EcoFlowStation | None = None
    power_topic: ForumTopicRegistry | None = None
    schedule_provider: OutageScheduleProvider | None = None
    outage_schedule_board: OutageScheduleBoard | None = None
    conservation_board: ConservationBoard | None = None
    shape_catalog: RouteShapeCatalog | None = None

    def build_posted_message_tracker(self) -> PostedMessageTracker:
        return PostedMessageTracker(bot=self.bot, uow_factory=self.uow_factory)


class JobRegistrar(Protocol):
    """A module's one scheduling entry point: given the scheduler and what was built, add whatever it needs."""

    def __call__(self, scheduler: AsyncIOScheduler, context: SchedulerContext) -> None:
        ...
