from aiogram import Router

from src.bot.handlers.transit import arrivals

router = Router(name="transit")
router.include_routers(arrivals.router)
