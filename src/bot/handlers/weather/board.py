import logging
from collections.abc import Callable
from datetime import datetime, tzinfo

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from src.bot.handlers.weather.formatting import render_climate_digest
from src.bot.handlers.weather.keyboards import build_weather_digest_keyboard
from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.bot.services.posted_message_tracker import WEATHER_DIGEST_KIND, PostedMessageTracker
from src.infrastructure.db.uow import UnitOfWork
from src.modules.room_climate.domain import RoomClimate
from src.modules.room_climate.use_cases.retrieve_room_climate import RetrieveRoomClimateUseCase
from src.modules.weather.domain import VentilationEffect, WeatherReport
from src.modules.weather.services.ventilation import resolve_ventilation_effect
from src.modules.weather.services.weather_provider import WeatherProvider

logger = logging.getLogger(__name__)

WEATHER_MODULE_NAME = "weather"

# a morning digest that boots late is still worth sending, but a stale one hours later is not
WEATHER_DIGEST_MISFIRE_GRACE_SECONDS = 2 * 60 * 60

# a bot may edit its own message for 48h; past that the morning digest is reposted rather than left stale
UNEDITABLE_MESSAGE_ERRORS = ("message to edit not found", "message can't be edited", "message_id_invalid")


class WeatherDigestBoard:
    """
    The климат digest as one self-editing message: posted each morning, then kept current in place through the
    day, so opening the topic shows the state right now, not the 08:00 snapshot. edits are silent — a glance,
    never a ping — and carry a "станом на HH:MM" footer so a live reading never reads as a stale one.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        weather_topic: ForumTopicRegistry,
        uow_factory: Callable[[], UnitOfWork],
        weather_provider: WeatherProvider,
        timezone: tzinfo,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.weather_topic = weather_topic
        self.uow_factory = uow_factory
        self.weather_provider = weather_provider
        self.timezone = timezone
        self.tracker = PostedMessageTracker(bot=bot, uow_factory=uow_factory)

    async def post(self) -> None:
        text = await self._render()
        if text is None:
            logger.warning("Weather digest skipped: no indoor reading and no forecast")
            return

        await self.tracker.clear(WEATHER_DIGEST_KIND)
        message = await self.bot.send_message(
            chat_id=self.chat_id,
            message_thread_id=await self.weather_topic.resolve(),
            text=text,
            reply_markup=build_weather_digest_keyboard(),
            # a glance, not a call to action — deliver and refresh it without a notification
            disable_notification=True,
        )
        await self.tracker.remember(WEATHER_DIGEST_KIND, message)
        logger.info("Posted the weather digest")

    async def refresh(self) -> bool:
        message_id = await self._remembered_message_id()
        if message_id is None:
            return False

        text = await self._render()
        if text is None:
            return False

        try:
            await self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=message_id,
                text=text,
                reply_markup=build_weather_digest_keyboard(),
            )
        except TelegramBadRequest as error:
            reason = str(error).lower()
            if "message is not modified" in reason:
                return True
            if not any(uneditable in reason for uneditable in UNEDITABLE_MESSAGE_ERRORS):
                raise
            # older than 48h — repost fresh so the topic keeps a live board
            await self.post()
        return True

    async def _render(self) -> str | None:
        indoor, outdoor, ventilation = await self._compose()
        if indoor is None and outdoor is None:
            return None
        return render_climate_digest(indoor, outdoor, ventilation, generated_at=datetime.now(self.timezone))

    async def _compose(self) -> tuple[RoomClimate | None, WeatherReport | None, VentilationEffect | None]:
        indoor = await RetrieveRoomClimateUseCase(uow=self.uow_factory())()
        # open-meteo throws transient 503s; on a miss show the last good reading (minutes old) rather than
        # blanking the digest to «погода недоступна» — the weather barely moves between 15-min refreshes
        outdoor = await self.weather_provider.fetch() or self.weather_provider.recent()

        ventilation = None
        if indoor is not None and outdoor is not None and outdoor.relative_humidity_percent is not None:
            ventilation = resolve_ventilation_effect(
                indoor_temperature_celsius=indoor.temperature_celsius,
                indoor_humidity_percent=indoor.relative_humidity_percent,
                outdoor_temperature_celsius=outdoor.temperature_celsius,
                outdoor_humidity_percent=outdoor.relative_humidity_percent,
            )
        return indoor, outdoor, ventilation

    async def _remembered_message_id(self) -> int | None:
        async with self.uow_factory() as uow:
            posted = await uow.posted_messages.list_by_kind(WEATHER_DIGEST_KIND)
        return posted[-1].message_id if posted else None
