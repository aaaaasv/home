from aiogram import Router

from src.bot.handlers.chores import items

router = Router(name="chores")
router.include_routers(items.router)
