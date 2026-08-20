from aiogram import Router

from src.bot.handlers.system import pi_status

SYSTEM_MODULE_NAME = "system"

router = Router(name="system")
router.include_routers(pi_status.router)
