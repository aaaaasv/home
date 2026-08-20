"""one-off: re-render today's weather digest and edit the message already posted in the topic.

the 2026-07-20 digest went out with no outdoor block because the pi could not resolve api.open-meteo.com.
this rebuilds the same text with the forecast in place and edits that message rather than posting a new one.
usage: python -m scripts.rerender_weather_digest <message_id>
"""

import asyncio
import logging
import sys

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.bot.dependencies import build_weather_provider
from src.bot.formatting import render_climate_digest
from src.common.config import Settings
from src.infrastructure.db.uow import UnitOfWork
from src.modules.plant_care.use_cases.retrieve_room_climate import RetrieveRoomClimateUseCase
from src.modules.weather.services.ventilation import resolve_ventilation_advice

logging.basicConfig(level=logging.INFO)


async def main(message_id: int) -> None:
    settings = Settings()
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    indoor = await RetrieveRoomClimateUseCase(uow=UnitOfWork())()
    outdoor = await build_weather_provider(settings).fetch()
    if outdoor is None:
        raise SystemExit(
            "the forecast is still unavailable — fix dns before rerunning, or the edit would change nothing"
        )

    ventilation = None
    if indoor is not None and outdoor.relative_humidity_percent is not None:
        ventilation = resolve_ventilation_advice(
            indoor_temperature_celsius=indoor.temperature_celsius,
            indoor_humidity_percent=indoor.relative_humidity_percent,
            outdoor_temperature_celsius=outdoor.temperature_celsius,
            outdoor_humidity_percent=outdoor.relative_humidity_percent,
        )

    text = render_climate_digest(indoor, outdoor, ventilation)
    print(text)
    await bot.edit_message_text(chat_id=settings.TELEGRAM_REMINDER_CHAT_ID, message_id=message_id, text=text)
    await bot.session.close()
    print(f"edited message {message_id}")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1])))
