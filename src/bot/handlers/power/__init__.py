from aiogram import Router

from src.bot.handlers.power import conservation, ecoflow, schedule

POWER_MODULE_NAME = "power"

router = Router(name="power")
router.include_routers(ecoflow.router, conservation.router, schedule.router)
