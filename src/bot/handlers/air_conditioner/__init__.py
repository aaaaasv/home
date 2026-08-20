from aiogram import Router

from src.bot.handlers.air_conditioner import card

router = Router(name="air_conditioner")
router.include_routers(card.router)
