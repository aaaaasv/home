from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.strategy import FSMStrategy

from src.bot import errors
from src.bot.dependencies import build_workflow_data
from src.bot.filters import HasAccessibleMessage, InModuleTopic
from src.bot.handlers import (
    assistant,
    chores,
    climate,
    places,
    plants,
    power,
    shopping,
    start,
    system,
    transit,
    wrong_topic,
)
from src.bot.handlers.chores.board import ChoresBoard
from src.bot.handlers.places.board import PlacesBoard
from src.bot.handlers.power.conservation_board import ConservationBoard
from src.bot.handlers.power.outage_schedule_board import OutageScheduleBoard
from src.bot.handlers.shopping.board import ShoppingListBoard
from src.bot.handlers.transit.board import TransitBoard
from src.bot.handlers.weather.board import WeatherDigestBoard
from src.bot.middlewares import AllowedUsersMiddleware, FamilyRosterMiddleware
from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.common.config import Settings
from src.infrastructure.db.uow import UnitOfWork
from src.modules.air_conditioner.services.air_conditioner import AirConditioner
from src.modules.assistant.use_cases.answer_question import AnswerQuestionUseCase
from src.modules.power.services.ecoflow_station import EcoFlowStation


def build_bot(settings: Settings) -> Bot:
    # silent by default: a reply to someone's own tap or command should never buzz the whole family's phones
    # the handful of genuine pushes — the care digest, comfort and deadline cards, price drops, the "AC left on"
    # and health alerts — opt back in with disable_notification=False, which keeps the ethos visible in the code
    return Bot(
        token=settings.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, disable_notification=True),
    )


def build_dispatcher(
    bot: Bot,
    settings: Settings,
    care_topic: ForumTopicRegistry,
    shopping_topic: ForumTopicRegistry,
    shopping_list_board: ShoppingListBoard,
    places_topic: ForumTopicRegistry,
    places_board: PlacesBoard,
    chores_topic: ForumTopicRegistry,
    chores_board: ChoresBoard,
    ecoflow_station: EcoFlowStation,
    air_conditioner: AirConditioner,
    weather_topic: ForumTopicRegistry | None = None,
    weather_digest_board: WeatherDigestBoard | None = None,
    tech_topic: ForumTopicRegistry | None = None,
    power_topic: ForumTopicRegistry | None = None,
    outage_schedule_board: OutageScheduleBoard | None = None,
    conservation_board: ConservationBoard | None = None,
    transit_topic: ForumTopicRegistry | None = None,
    transit_board: TransitBoard | None = None,
    assistant_topic: ForumTopicRegistry | None = None,
    answer_question: AnswerQuestionUseCase | None = None,
) -> Dispatcher:
    # scope the fsm to the topic, so an /add started in one topic cannot swallow text typed in another
    dispatcher = Dispatcher(
        storage=MemoryStorage(),
        fsm_strategy=FSMStrategy.USER_IN_TOPIC,
        **build_workflow_data(
            bot=bot,
            settings=settings,
            shopping_list_board=shopping_list_board,
            places_board=places_board,
            chores_board=chores_board,
            ecoflow_station=ecoflow_station,
            air_conditioner=air_conditioner,
            weather_digest_board=weather_digest_board,
            outage_schedule_board=outage_schedule_board,
            conservation_board=conservation_board,
            transit_board=transit_board,
            answer_question=answer_question,
        ),
    )
    dispatcher.update.outer_middleware(AllowedUsersMiddleware(settings.allowed_telegram_user_ids))
    # after the allowlist has set the actor, remember who wrote — the roster that tags a chore to a person by name
    dispatcher.message.middleware(FamilyRosterMiddleware(UnitOfWork))

    # the topic is what tells one module's plain text and /add from another's
    plants.router.message.filter(InModuleTopic(care_topic))
    plants.router.callback_query.filter(HasAccessibleMessage())
    shopping.router.message.filter(InModuleTopic(shopping_topic))
    shopping.router.callback_query.filter(HasAccessibleMessage())
    places.router.message.filter(InModuleTopic(places_topic))
    places.router.callback_query.filter(HasAccessibleMessage())
    chores.router.message.filter(InModuleTopic(chores_topic))
    chores.router.callback_query.filter(HasAccessibleMessage())

    module_routers = [plants.router, shopping.router, places.router, chores.router]
    # without a topic the module has no namespace, so it must stay silent rather than answer everywhere
    if weather_topic is not None:
        climate.router.message.filter(InModuleTopic(weather_topic))
        climate.router.callback_query.filter(HasAccessibleMessage())
        module_routers.append(climate.router)
    if tech_topic is not None:
        system.router.message.filter(InModuleTopic(tech_topic))
        module_routers.append(system.router)
    if power_topic is not None:
        power.router.message.filter(InModuleTopic(power_topic))
        power.router.callback_query.filter(HasAccessibleMessage())
        module_routers.append(power.router)
    if transit_topic is not None:
        transit.router.message.filter(InModuleTopic(transit_topic))
        transit.router.callback_query.filter(HasAccessibleMessage())
        module_routers.append(transit.router)
    if assistant_topic is not None:
        # text-only module: plain text is a question, so no command menu and no callbacks to filter
        assistant.router.message.filter(InModuleTopic(assistant_topic))
        module_routers.append(assistant.router)

    # start first — /cancel must beat the add-plant flow, which swallows plain text
    # wrong_topic last — it only answers what every module router declined
    dispatcher.include_routers(
        start.router,
        *module_routers,
        wrong_topic.router,
        errors.router,
    )
    return dispatcher
