from aiogram import Router

from src.bot.handlers.power import conservation, ecoflow, reserve, schedule

POWER_MODULE_NAME = "power"

router = Router(name="power")
router.include_routers(ecoflow.router, reserve.router, conservation.router, schedule.router)
