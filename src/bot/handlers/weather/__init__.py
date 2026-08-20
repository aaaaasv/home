from aiogram import Router

from src.bot.handlers.weather import digest

router = Router(name="weather")
router.include_routers(digest.router)
