from aiogram import Router

from src.bot.handlers.shopping import items

router = Router(name="shopping")
router.include_routers(items.router)
