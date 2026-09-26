"""Delivery for the sensors module: the flat's own air, on request only."""
from aiogram import Router

from src.bot.handlers.sensors import card

SENSORS_MODULE_NAME = "sensors"

router = Router(name="sensors")
router.include_routers(card.router)
