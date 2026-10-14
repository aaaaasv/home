"""No commands: the module watches a feed, moves one light and posts one card.

The router exists for the single button that card carries. Nothing here is filtered by topic — a callback
names its own module in its prefix, and the card lives in 🚨 тривога while the strip belongs to ⚡ світло.
"""
from aiogram import Router

from src.bot.handlers.air_alert import strip

AIR_ALERT_MODULE_NAME = "air_alert"

router = Router(name="air_alert")
router.include_routers(strip.router)
