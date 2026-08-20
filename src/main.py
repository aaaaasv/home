import asyncio
import logging
from datetime import timedelta

from aiogram.types import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats

from src.bot.application import build_bot, build_dispatcher
from src.bot.dependencies import (
    build_air_conditioner,
    build_answer_question,
    build_compose_transit_report,
    build_ecoflow_station,
    build_language_model,
    build_pi_health_sensor,
    build_presence_source,
    build_price_source,
    build_room_climate_sensor,
    build_shape_catalog,
    build_weather_provider,
    build_yasno_schedule_provider,
)
from src.bot.handlers.assistant import ASSISTANT_MODULE_NAME
from src.bot.handlers.chores.board import CHORES_MODULE_NAME, ChoresBoard
from src.bot.handlers.places.board import PLACES_MODULE_NAME, PlacesBoard
from src.bot.handlers.plants import PLANTS_MODULE_NAME
from src.bot.handlers.power import POWER_MODULE_NAME
from src.bot.handlers.power.conservation_board import ConservationBoard
from src.bot.handlers.power.outage_schedule_board import OutageScheduleBoard
from src.bot.handlers.shopping.board import SHOPPING_MODULE_NAME, ShoppingListBoard
from src.bot.handlers.system import SYSTEM_MODULE_NAME
from src.bot.handlers.transit.board import TRANSIT_MODULE_NAME, TransitBoard
from src.bot.handlers.weather.board import WEATHER_MODULE_NAME, WeatherDigestBoard
from src.bot.preflight import verify_reminder_chat
from src.bot.reminders import build_scheduler
from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.common.config import Settings, get_settings
from src.common.household_calendar import HouseholdCalendar
from src.infrastructure.db.uow import UnitOfWork

logger = logging.getLogger(__name__)

# telegram scopes the command menu per chat at best — never per topic — so the group menu is one flat list
# and the wording of a shared command has to hold in every topic
GROUP_COMMANDS = [
    BotCommand(command="list", description="показати список цього топіка"),
    BotCommand(command="add", description="додати запис у цей топік"),
    BotCommand(command="today", description="🪴 що треба зробити сьогодні"),
    BotCommand(command="history", description="🪴 останні дії"),
    BotCommand(command="later", description="🛒 покупка на колись"),
    BotCommand(command="track", description="🛒 стежити за ціною (лінк hotline)"),
    BotCommand(command="ac", description="❄️ кондиціонер"),
    BotCommand(command="eco", description="⚡ EcoFlow Delta 2"),
    BotCommand(command="conserve", description="⚡ зберігання EcoFlow"),
    BotCommand(command="pi", description="🩺 стан Raspberry Pi"),
    BotCommand(command="bus", description="🚌 коли транспорт із зупинки"),
    BotCommand(command="help", description="що в якому топіку"),
    BotCommand(command="cancel", description="скасувати поточну дію"),
]

# a private chat has no topics, so no module can claim /add there
PRIVATE_COMMANDS = [
    BotCommand(command="start", description="про бота"),
    BotCommand(command="help", description="про бота"),
]


def build_forum_topic(bot, settings: Settings, module_name: str, title: str, topic_id: int | None):
    return ForumTopicRegistry(
        bot=bot,
        chat_id=settings.TELEGRAM_REMINDER_CHAT_ID,
        module_name=module_name,
        title=title,
        configured_topic_id=topic_id,
        uow_factory=UnitOfWork,
    )


async def run() -> None:
    settings = get_settings()
    # force=True because greeclimate installs a root handler on import, and basicConfig is a no-op once one exists
    logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s — %(message)s", force=True)
    # greeclimate logs the unit's aes bind key at info on every bind, and the driver re-binds on every poll —
    # pin it above info so the key that grants lan control never lands in the container logs
    logging.getLogger("greeclimate").setLevel(logging.WARNING)

    bot = build_bot(settings)
    # crash loudly rather than poll a chat the bot cannot serve: that silence cost the family several days of digests
    await verify_reminder_chat(bot, settings.TELEGRAM_REMINDER_CHAT_ID)

    care_topic = build_forum_topic(
        bot, settings, PLANTS_MODULE_NAME, settings.PLANTS_TOPIC_TITLE, settings.plants_topic_id
    )
    shopping_topic = build_forum_topic(
        bot, settings, SHOPPING_MODULE_NAME, settings.SHOPPING_TOPIC_TITLE, settings.shopping_topic_id
    )
    shopping_list_board = ShoppingListBoard(
        bot=bot,
        chat_id=settings.TELEGRAM_REMINDER_CHAT_ID,
        forum_topic=shopping_topic,
        uow_factory=UnitOfWork,
    )
    places_topic = build_forum_topic(
        bot, settings, PLACES_MODULE_NAME, settings.PLACES_TOPIC_TITLE, settings.places_topic_id
    )
    places_board = PlacesBoard(
        bot=bot,
        chat_id=settings.TELEGRAM_REMINDER_CHAT_ID,
        forum_topic=places_topic,
        uow_factory=UnitOfWork,
    )
    chores_topic = build_forum_topic(
        bot, settings, CHORES_MODULE_NAME, settings.CHORES_TOPIC_TITLE, settings.chores_topic_id
    )
    chores_board = ChoresBoard(
        bot=bot,
        chat_id=settings.TELEGRAM_REMINDER_CHAT_ID,
        forum_topic=chores_topic,
        uow_factory=UnitOfWork,
        household_calendar=HouseholdCalendar(timezone=settings.timezone),
    )
    # the climate topic houses both the weather digest and /ac, so stand it up if either is on
    weather_topic = None
    weather_provider = None
    if settings.WEATHER_DIGEST_ENABLED or settings.AIR_CONDITIONER_ENABLED:
        weather_topic = build_forum_topic(
            bot, settings, WEATHER_MODULE_NAME, settings.WEATHER_TOPIC_TITLE, settings.weather_topic_id
        )
    weather_digest_board = None
    if settings.WEATHER_DIGEST_ENABLED and weather_topic is not None:
        weather_provider = build_weather_provider(settings)
        weather_digest_board = WeatherDigestBoard(
            bot=bot,
            chat_id=settings.TELEGRAM_REMINDER_CHAT_ID,
            weather_topic=weather_topic,
            uow_factory=UnitOfWork,
            weather_provider=weather_provider,
            timezone=settings.timezone,
        )

    # a push-only topic for the pi's own alerts — no router, since nothing there listens for a command
    tech_topic = None
    if settings.SYSTEM_HEALTH_ENABLED:
        tech_topic = build_forum_topic(
            bot, settings, SYSTEM_MODULE_NAME, settings.TECH_TOPIC_TITLE, settings.tech_topic_id
        )

    # ⚡ світло: ecoflow (ble) and the yasno schedule share the topic — stand it up if either is on. the station
    # hold a reading cache, so one instance is shared by the /eco card and the poll job
    ecoflow_station = build_ecoflow_station(settings)
    # the unit serves one client at a time, so the button handlers and the runtime poll must share one instance —
    # its lock only serialises binds that go through the same object
    air_conditioner = build_air_conditioner(settings)
    power_topic = None
    if settings.ECOFLOW_ENABLED or settings.YASNO_ENABLED:
        power_topic = build_forum_topic(
            bot, settings, POWER_MODULE_NAME, settings.POWER_TOPIC_TITLE, settings.power_topic_id
        )
    schedule_provider = build_yasno_schedule_provider(settings)
    outage_schedule_board = None
    if schedule_provider is not None and power_topic is not None:
        outage_schedule_board = OutageScheduleBoard(
            bot=bot,
            chat_id=settings.TELEGRAM_REMINDER_CHAT_ID,
            power_topic=power_topic,
            uow_factory=UnitOfWork,
            schedule_provider=schedule_provider,
            timezone=settings.timezone,
        )
    # the conservation card belongs to the ecoflow station; shared by the /eco toggle and the 4-hourly refresh
    conservation_board = None
    if settings.ECOFLOW_ENABLED and power_topic is not None:
        conservation_board = ConservationBoard(
            bot=bot,
            chat_id=settings.TELEGRAM_REMINDER_CHAT_ID,
            power_topic=power_topic,
            uow_factory=UnitOfWork,
            timezone=settings.timezone,
        )

    # transit: an on-demand arrival card in its own topic — built only when on. the shape catalog is shared by
    # the weekly refresh job and the use case; the board owns the short refresh window that polls the live feed
    transit_topic = None
    shape_catalog = None
    transit_board = None
    if settings.TRANSIT_ENABLED:
        transit_topic = build_forum_topic(
            bot, settings, TRANSIT_MODULE_NAME, settings.TRANSIT_TOPIC_TITLE, settings.transit_topic_id
        )
        shape_catalog = build_shape_catalog(settings)
        transit_board = TransitBoard(
            bot=bot,
            chat_id=settings.TELEGRAM_REMINDER_CHAT_ID,
            transit_topic=transit_topic,
            uow_factory=UnitOfWork,
            compose_transit_report=build_compose_transit_report(settings, shape_catalog),
            timezone=settings.timezone,
            refresh_interval=timedelta(seconds=settings.TRANSIT_CARD_REFRESH_SECONDS),
            refresh_window=timedelta(minutes=settings.TRANSIT_CARD_WINDOW_MINUTES),
        )

    # the assistant: a grounded home helper — the topic exists only when it can actually answer (model + key set)
    assistant_topic = None
    answer_question = None
    if settings.ASSISTANT_ENABLED:
        answer_question = build_answer_question(settings, build_language_model(settings))
        if answer_question is not None:
            assistant_topic = build_forum_topic(
                bot, settings, ASSISTANT_MODULE_NAME, settings.ASSISTANT_TOPIC_TITLE, settings.assistant_topic_id
            )

    dispatcher = build_dispatcher(
        bot=bot,
        settings=settings,
        care_topic=care_topic,
        shopping_topic=shopping_topic,
        shopping_list_board=shopping_list_board,
        places_topic=places_topic,
        places_board=places_board,
        chores_topic=chores_topic,
        chores_board=chores_board,
        weather_topic=weather_topic,
        weather_digest_board=weather_digest_board,
        tech_topic=tech_topic,
        ecoflow_station=ecoflow_station,
        power_topic=power_topic,
        outage_schedule_board=outage_schedule_board,
        conservation_board=conservation_board,
        transit_topic=transit_topic,
        transit_board=transit_board,
        assistant_topic=assistant_topic,
        answer_question=answer_question,
        air_conditioner=air_conditioner,
    )
    scheduler = build_scheduler(
        bot=bot,
        settings=settings,
        household_calendar=HouseholdCalendar(timezone=settings.timezone),
        care_topic=care_topic,
        shopping_topic=shopping_topic,
        chores_topic=chores_topic,
        room_climate_sensor=build_room_climate_sensor(settings),
        price_source=build_price_source(settings),
        weather_topic=weather_topic,
        weather_digest_board=weather_digest_board,
        air_conditioner=air_conditioner,
        tech_topic=tech_topic,
        pi_health_sensor=build_pi_health_sensor(settings),
        presence_source=build_presence_source(settings),
        ecoflow_station=ecoflow_station,
        power_topic=power_topic,
        schedule_provider=schedule_provider,
        outage_schedule_board=outage_schedule_board,
        conservation_board=conservation_board,
        shape_catalog=shape_catalog,
    )

    # drop the pre-topic default list, which the two scoped lists below now replace
    await bot.delete_my_commands()
    await bot.set_my_commands(GROUP_COMMANDS, scope=BotCommandScopeAllGroupChats())
    await bot.set_my_commands(PRIVATE_COMMANDS, scope=BotCommandScopeAllPrivateChats())

    # resolve before polling: the topic filter reads the resolved id on every update
    logger.info("Plant care topic: %s", await care_topic.resolve())
    logger.info("Shopping topic: %s", await shopping_topic.resolve())
    logger.info("Places topic: %s", await places_topic.resolve())
    logger.info("Chores topic: %s", await chores_topic.resolve())
    if weather_topic is not None:
        logger.info("Weather topic: %s", await weather_topic.resolve())
    if tech_topic is not None:
        logger.info("Tech topic: %s", await tech_topic.resolve())
    if power_topic is not None:
        logger.info("Power topic: %s", await power_topic.resolve())
    if transit_topic is not None:
        logger.info("Transit topic: %s", await transit_topic.resolve())
    if assistant_topic is not None:
        logger.info("Assistant topic: %s", await assistant_topic.resolve())

    # hold the ecoflow ble link open in the background so /eco reads and control are instant, not a scan+connect
    await ecoflow_station.start()
    scheduler.start()
    logger.info("Digest scheduled at %s %s", settings.DAILY_DIGEST_TIME, settings.TIMEZONE)

    try:
        await dispatcher.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await ecoflow_station.stop()
        if transit_board is not None:
            await transit_board.stop()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run())
