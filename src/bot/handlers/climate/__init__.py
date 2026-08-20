from aiogram import Router

from src.bot.handlers import air_conditioner, weather

# климат is one topic shared by two modules: the morning digest and the /ac card
router = Router(name="climate")
router.include_routers(air_conditioner.router, weather.router)
