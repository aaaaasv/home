"""Putting the alert strip out from the card that pinged, without disturbing what that card says."""
import logging

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from src.bot.handlers.air_alert.keyboards import AlertStripCallback
from src.bot.handlers.air_alert.messages import AIR_ALERT_STRIP_OFF_TOAST
from src.modules.lighting.services.panel_light import PanelLight

logger = logging.getLogger(__name__)

router = Router(name="air_alert_strip")


@router.callback_query(AlertStripCallback.filter())
async def put_the_strip_out(callback: CallbackQuery, panel_light: PanelLight) -> None:
    """
    The card keeps its text and loses its button: it is the record of an alert, not a light switch.

    this is why it is not the `/light` button: that one redraws the card it was tapped on, which is right
    for its own card and would replace «червона тривога, о 19:39» with «стрічка не горить» on the one
    message somebody has just been woken by.
    """
    await panel_light.set_brightness(0)
    logger.info("The alert strip was put out from the alert card")

    await callback.answer(AIR_ALERT_STRIP_OFF_TOAST)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        # the card may have been deleted by hand, and the strip obeyed either way
        pass
