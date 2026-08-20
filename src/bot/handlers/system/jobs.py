"""The scheduled job that watches the Pi's own health."""
import logging

from aiogram import Bot

from src.bot.handlers.system.formatting import render_system_health_alert
from src.bot.services.forum_topic_registry import ForumTopicRegistry
from src.common.config import Settings
from src.modules.system_health.monitor import SystemHealthMonitor
from src.modules.system_health.services.pi_health_sensor import PiHealthSensor

logger = logging.getLogger(__name__)


class SystemHealthJob:
    """
    Watches the pi's own vitals and speaks only when one crosses into trouble — under-voltage, overheating, or a
    filling disk. it posts to a technical topic no one else uses, and stays silent the rest of the time.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        tech_topic: ForumTopicRegistry,
        sensor: PiHealthSensor,
        settings: Settings,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.tech_topic = tech_topic
        self.sensor = sensor
        self.monitor = SystemHealthMonitor(
            temperature_alert_celsius=settings.PI_TEMPERATURE_ALERT_CELSIUS,
            temperature_recovery_celsius=settings.PI_TEMPERATURE_RECOVERY_CELSIUS,
            disk_alert_percent=settings.PI_DISK_ALERT_PERCENT,
            disk_recovery_percent=settings.PI_DISK_RECOVERY_PERCENT,
        )

    async def __call__(self) -> None:
        reading = await self.sensor.read()
        if reading is None:
            return

        issues = self.monitor.evaluate(reading)
        if not issues:
            return

        await self.bot.send_message(
            chat_id=self.chat_id,
            message_thread_id=await self.tech_topic.resolve(),
            text=render_system_health_alert(issues),
            # under-voltage or overheating can damage the pi and its card — worth a ping even in the tech topic
            disable_notification=False,
        )
        logger.info("Reported %s system health issue(s)", len(issues))
