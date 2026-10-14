from aiogram import Router

from src.bot.handlers.lighting import strip

LIGHTING_MODULE_NAME = "lighting"

router = Router(name="lighting")
router.include_routers(strip.router)
