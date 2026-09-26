from aiogram import Router

from src.bot.handlers import air_conditioner, sensors, weather

# климат is one topic shared by three modules: the morning digest, the /ac card and the sensors' own /climate
router = Router(name="climate")
router.include_routers(air_conditioner.router, weather.router, sensors.router)
