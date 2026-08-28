from datetime import timedelta
from pathlib import Path
from typing import Any

from aiogram import Bot

from src.bot.handlers.chores.board import ChoresBoard
from src.bot.handlers.places.board import PlacesBoard
from src.bot.handlers.plants.claude_photo_analyst import ClaudePhotoAnalyst
from src.bot.handlers.plants.gemini_photo_analyst import GeminiPhotoAnalyst
from src.bot.handlers.plants.gemini_plant_identifier import GeminiPlantIdentifier
from src.bot.handlers.power.conservation_board import ConservationBoard
from src.bot.handlers.power.outage_schedule_board import OutageScheduleBoard
from src.bot.handlers.shopping.board import ShoppingListBoard
from src.bot.handlers.transit.board import TransitBoard
from src.bot.handlers.weather.board import WeatherDigestBoard
from src.bot.services.posted_message_tracker import PostedMessageTracker
from src.bot.services.telegram_photo_storage import TelegramPhotoStorage
from src.common.config import Settings
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.adapters.alarm_map_air_raid_alert_source import AlarmMapAirRaidAlertSource
from src.infrastructure.adapters.ecoflow_ble_station import EcoFlowBleStation
from src.infrastructure.adapters.gemini_language_model import GeminiLanguageModel
from src.infrastructure.adapters.gree_air_conditioner import GreeAirConditioner
from src.infrastructure.adapters.gtfs_realtime_feed import GtfsRealtimeFeed
from src.infrastructure.adapters.gtfs_static_shape_catalog import GtfsStaticShapeCatalog
from src.infrastructure.adapters.hotline_price_source import HotlinePriceSource
from src.infrastructure.adapters.open_meteo_weather_provider import OpenMeteoWeatherProvider
from src.infrastructure.adapters.router_presence_source import RouterPresenceSource
from src.infrastructure.adapters.sht31_room_climate_sensor import Sht31RoomClimateSensor
from src.infrastructure.adapters.sysfs_pi_health_sensor import SysfsPiHealthSensor
from src.infrastructure.adapters.yasno_schedule_provider import YasnoScheduleProvider
from src.infrastructure.db.uow import UnitOfWork
from src.modules.air_conditioner.services.air_conditioner import AirConditioner, NullAirConditioner
from src.modules.assistant.services.conversation_memory import ConversationMemory
from src.modules.assistant.services.knowledge_source import FileKnowledgeSource
from src.modules.assistant.services.language_model import LanguageModel
from src.modules.assistant.use_cases.answer_question import AnswerQuestionUseCase
from src.modules.plant_care.services.photo_analyst import PhotoAnalyst
from src.modules.plant_care.services.photo_storage import NullPhotoStorage, PhotoStorage
from src.modules.plant_care.services.plant_identifier import PlantIdentifier
from src.modules.power.services.ecoflow_station import EcoFlowStation, NullEcoFlowStation
from src.modules.presence.services.presence_source import NullPresenceSource, PresenceSource
from src.modules.room_climate.services.room_climate_sensor import NullRoomClimateSensor, RoomClimateSensor
from src.modules.shopping.domain import ReputabilityPolicy
from src.modules.system_health.services.pi_health_sensor import NullPiHealthSensor, PiHealthSensor
from src.modules.transit.domain import GeoPoint, StopLocation, parse_watched_routes
from src.modules.transit.services.arrival_estimator import ArrivalEstimator
from src.modules.transit.use_cases.compose_transit_report import ComposeTransitReportUseCase
from src.modules.weather.services.weather_provider import NullWeatherProvider, WeatherProvider


def build_photo_storage(bot: Bot, settings: Settings) -> PhotoStorage:
    if not settings.PHOTO_STORAGE_PATH:
        return NullPhotoStorage()
    return TelegramPhotoStorage(bot=bot, storage_path=Path(settings.PHOTO_STORAGE_PATH))


def build_room_climate_sensor(settings: Settings) -> RoomClimateSensor:
    # the bot must run fine with no sensor wired in — that is the normal state until the hardware arrives
    if not settings.CLIMATE_SENSOR_ENABLED:
        return NullRoomClimateSensor()

    return Sht31RoomClimateSensor(
        bus_number=settings.CLIMATE_SENSOR_I2C_BUS, address=settings.CLIMATE_SENSOR_I2C_ADDRESS
    )


def build_weather_provider(settings: Settings) -> WeatherProvider:
    if not settings.WEATHER_DIGEST_ENABLED:
        return NullWeatherProvider()

    return OpenMeteoWeatherProvider(
        latitude=settings.WEATHER_LATITUDE,
        longitude=settings.WEATHER_LONGITUDE,
        timezone_name=settings.TIMEZONE,
    )


def build_air_conditioner(settings: Settings) -> AirConditioner:
    if not settings.AIR_CONDITIONER_ENABLED:
        return NullAirConditioner()

    return GreeAirConditioner(
        host=settings.AIR_CONDITIONER_HOST,
        mac=settings.AIR_CONDITIONER_MAC,
        name=settings.AIR_CONDITIONER_ROOM,
    )


def build_ecoflow_station(settings: Settings) -> EcoFlowStation:
    # the station holds a reading cache, so the whole process must share one instance — build it once in main and
    # thread it into both the dispatcher and the scheduler rather than newing it up per caller
    if not settings.ECOFLOW_ENABLED or not settings.ECOFLOW_USER_ID or not settings.ECOFLOW_BLE_MAC:
        return NullEcoFlowStation()

    return EcoFlowBleStation(
        user_id=settings.ECOFLOW_USER_ID,
        ble_mac=settings.ECOFLOW_BLE_MAC,
        timezone=settings.timezone,
        scan_seconds=settings.ECOFLOW_BLE_SCAN_SECONDS,
    )


def build_yasno_schedule_provider(settings: Settings) -> YasnoScheduleProvider | None:
    # not a null object: the board and poll job are only created when a provider exists, so absence is the off switch
    if not settings.YASNO_ENABLED:
        return None

    return YasnoScheduleProvider(
        group=settings.YASNO_GROUP,
        timezone_name=settings.TIMEZONE,
        region_id=settings.YASNO_REGION_ID,
        dso_id=settings.YASNO_DSO_ID,
    )


def build_pi_health_sensor(settings: Settings) -> PiHealthSensor:
    if not settings.SYSTEM_HEALTH_ENABLED:
        return NullPiHealthSensor()

    return SysfsPiHealthSensor(data_path=str(Path(settings.DATABASE_PATH).parent) or ".")


def build_price_source(settings: Settings) -> HotlinePriceSource:
    return HotlinePriceSource(
        policy=ReputabilityPolicy(
            minimum_rating=settings.HOTLINE_MINIMUM_RATING,
            minimum_reviews=settings.HOTLINE_MINIMUM_REVIEWS,
            trusted_firm_ids=settings.hotline_trusted_firm_ids,
        ),
        donor_category_url=settings.HOTLINE_DONOR_CATEGORY_URL,
        city_id=settings.HOTLINE_CITY_ID,
    )


def build_photo_analyst(settings: Settings) -> PhotoAnalyst | None:
    # not a null object like the sensors: the handler must know whether to promise the user a verdict at all
    # prefer the free gemini; fall back to anthropic only when that is the key on file
    if not settings.PLANT_PHOTO_REVIEW_ENABLED:
        return None
    if settings.GEMINI_API_KEY:
        return GeminiPhotoAnalyst(api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_MODEL)
    if settings.ANTHROPIC_API_KEY:
        return ClaudePhotoAnalyst(api_key=settings.ANTHROPIC_API_KEY, model=settings.PLANT_PHOTO_REVIEW_MODEL)
    return None


def build_plant_identifier(settings: Settings) -> PlantIdentifier | None:
    # None rather than a null object, the same way the analyst is: the add-plant flow must know whether it can
    # offer to name the plant at all, or should go straight to asking
    if not settings.PLANT_IDENTIFICATION_ENABLED or not settings.GEMINI_API_KEY:
        return None
    return GeminiPlantIdentifier(api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_MODEL)


def build_presence_source(settings: Settings) -> PresenceSource:
    if not settings.PRESENCE_ENABLED or not settings.ROUTER_PASSWORD:
        return NullPresenceSource()

    return RouterPresenceSource(
        host=settings.ROUTER_HOST, username=settings.ROUTER_USERNAME, password=settings.ROUTER_PASSWORD
    )


def build_shape_catalog(settings: Settings) -> GtfsStaticShapeCatalog | None:
    # not a null object: the weekly refresh job and the use case are built only when a catalog exists
    if not settings.TRANSIT_ENABLED:
        return None

    watched_routes = parse_watched_routes(settings.TRANSIT_ROUTES)
    return GtfsStaticShapeCatalog(
        url=settings.TRANSIT_STATIC_URL,
        cache_path=Path(settings.DATABASE_PATH).parent / settings.TRANSIT_STATIC_CACHE_PATH,
        stop=GeoPoint(latitude=settings.TRANSIT_STOP_LATITUDE, longitude=settings.TRANSIT_STOP_LONGITUDE),
        destination=GeoPoint(
            latitude=settings.TRANSIT_DESTINATION_LATITUDE, longitude=settings.TRANSIT_DESTINATION_LONGITUDE
        ),
        watched_route_ids=frozenset(route.route_id for route in watched_routes),
        refresh_after=timedelta(days=settings.TRANSIT_STATIC_REFRESH_DAYS),
    )


def build_compose_transit_report(
    settings: Settings, shape_catalog: GtfsStaticShapeCatalog | None
) -> ComposeTransitReportUseCase | None:
    if not settings.TRANSIT_ENABLED or shape_catalog is None:
        return None

    watched_routes = parse_watched_routes(settings.TRANSIT_ROUTES)
    stop = StopLocation(
        stop_id=settings.TRANSIT_STOP_ID,
        location=GeoPoint(latitude=settings.TRANSIT_STOP_LATITUDE, longitude=settings.TRANSIT_STOP_LONGITUDE),
    )
    # the estimator holds poll-to-poll progress, so this one shared instance is threaded through the use case
    return ComposeTransitReportUseCase(
        realtime_feed=GtfsRealtimeFeed(
            url=settings.TRANSIT_REALTIME_URL,
            watched_route_ids=frozenset(route.route_id for route in watched_routes),
        ),
        shape_catalog=shape_catalog,
        arrival_estimator=ArrivalEstimator(stop=stop, watched_routes=watched_routes),
        air_raid_alert_source=AlarmMapAirRaidAlertSource(),
        watched_routes=watched_routes,
    )


def build_language_model(settings: Settings) -> LanguageModel | None:
    # not a null object: the topic and use case are built only when a model exists, so absence is the off switch
    if not settings.ASSISTANT_ENABLED or not settings.GEMINI_API_KEY:
        return None

    return GeminiLanguageModel(api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_MODEL)


def build_answer_question(settings: Settings, language_model: LanguageModel | None) -> AnswerQuestionUseCase | None:
    if not settings.ASSISTANT_ENABLED or language_model is None:
        return None

    knowledge_source = FileKnowledgeSource(knowledge_path=Path(settings.ASSISTANT_KNOWLEDGE_PATH))
    # one use case lives for the whole process, so its memory of the conversation lives that long too
    return AnswerQuestionUseCase(
        language_model=language_model,
        knowledge_source=knowledge_source,
        conversation_memory=ConversationMemory(),
    )


def build_workflow_data(
    bot: Bot,
    settings: Settings,
    shopping_list_board: ShoppingListBoard,
    places_board: PlacesBoard,
    chores_board: ChoresBoard,
    ecoflow_station: EcoFlowStation,
    air_conditioner: AirConditioner,
    weather_digest_board: WeatherDigestBoard | None = None,
    outage_schedule_board: OutageScheduleBoard | None = None,
    conservation_board: ConservationBoard | None = None,
    transit_board: TransitBoard | None = None,
    answer_question: AnswerQuestionUseCase | None = None,
) -> dict[str, Any]:
    return {
        "settings": settings,
        "uow_factory": UnitOfWork,
        "household_calendar": HouseholdCalendar(timezone=settings.timezone),
        "photo_storage": build_photo_storage(bot=bot, settings=settings),
        "photo_analyst": build_photo_analyst(settings),
        "plant_identifier": build_plant_identifier(settings),
        "price_source": build_price_source(settings),
        "shopping_list_board": shopping_list_board,
        "places_board": places_board,
        "chores_board": chores_board,
        "weather_digest_board": weather_digest_board,
        "outage_schedule_board": outage_schedule_board,
        "conservation_board": conservation_board,
        "transit_board": transit_board,
        "answer_question": answer_question,
        "air_conditioner": air_conditioner,
        "ecoflow_station": ecoflow_station,
        "weather_provider": build_weather_provider(settings),
        "pi_health_sensor": build_pi_health_sensor(settings),
        "posted_message_tracker": PostedMessageTracker(bot=bot, uow_factory=UnitOfWork),
    }
