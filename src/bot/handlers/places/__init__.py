from aiogram import Router

from src.bot.handlers.places import items

router = Router(name="places")
router.include_routers(items.router)
