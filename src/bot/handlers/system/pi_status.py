from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.bot.handlers.system import messages
from src.bot.handlers.system.formatting import render_pi_health
from src.modules.system_health.services.pi_health_sensor import PiHealthSensor

router = Router(name="pi_status")


@router.message(Command("pi"))
async def show_pi_status(message: Message, pi_health_sensor: PiHealthSensor) -> None:
    reading = await pi_health_sensor.read()
    if reading is None:
        await message.answer(messages.PI_STATUS_UNAVAILABLE)
        return

    await message.answer(render_pi_health(reading))
