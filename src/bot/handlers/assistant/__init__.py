from aiogram import Router

from src.bot.handlers.assistant import ask

ASSISTANT_MODULE_NAME = "assistant"

router = Router(name="assistant")
router.include_routers(ask.router)
