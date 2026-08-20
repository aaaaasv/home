from aiogram import Router
from aiogram.types import CallbackQuery

from src.bot.handlers.weather.board import WeatherDigestBoard
from src.bot.handlers.weather.keyboards import WeatherDigestCallback
from src.bot.handlers.weather.messages import WEATHER_DIGEST_REFRESHING

router = Router(name="weather_digest")


@router.callback_query(WeatherDigestCallback.filter())
async def refresh_weather_digest(callback: CallbackQuery, weather_digest_board: WeatherDigestBoard) -> None:
    # a status banner up front while the forecast is fetched; the refreshed card itself is the result
    await callback.answer(WEATHER_DIGEST_REFRESHING)
    await weather_digest_board.refresh()
