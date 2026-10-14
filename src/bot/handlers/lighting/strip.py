"""Driving the shelf strip from the group, because the home app is not always reachable."""
import logging

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from src.bot.handlers.lighting.formatting import render_strip
from src.bot.handlers.lighting.keyboards import StripCallback, build_strip_keyboard
from src.bot.handlers.lighting.messages import LIGHT_STRIP_CARD_EXPIRED, LIGHT_STRIP_UNREACHABLE
from src.bot.services.posted_message_tracker import STRIP_CARD_KIND, PostedMessageTracker
from src.modules.lighting.domain import PanelLightState
from src.modules.lighting.services.panel_light import PanelLight

logger = logging.getLogger(__name__)

router = Router(name="strip")


@router.message(Command("light"))
async def show_strip(
    message: Message,
    panel_light: PanelLight,
    posted_message_tracker: PostedMessageTracker,
) -> None:
    """
    The strip's card, with the level it stands at and the buttons to move it.

    it exists for the night of 13/14.10: a red alert raised the strip, the home app could not be reached from
    either band of the wi-fi, and the only way left to put it out was to climb up and unplug it. telegram
    reaches the bot over the internet, which was up the whole of that night.
    """
    state = await panel_light.read()
    if state is None:
        await message.answer(LIGHT_STRIP_UNREACHABLE)
        return

    # drop the previous card: its buttons name levels, and two cards would disagree about where the strip is
    await posted_message_tracker.clear(STRIP_CARD_KIND)
    card = await message.answer(render_strip(state), reply_markup=build_strip_keyboard(state))
    await posted_message_tracker.remember(STRIP_CARD_KIND, card)


@router.callback_query(StripCallback.filter())
async def set_strip(callback: CallbackQuery, callback_data: StripCallback, panel_light: PanelLight) -> None:
    """Put the strip where the button says, and redraw the card around the level that was asked for."""
    await panel_light.set_brightness(callback_data.percent)
    logger.info("The strip was set to %d%% from the group", callback_data.percent)

    # drawn from the level we asked for rather than from a fresh read: the host service looks at its command
    # file every fifth of a second, so reading it back at once answers with the level we have just replaced
    asked_for = PanelLightState(is_on=callback_data.percent > 0, brightness_percent=callback_data.percent)
    await callback.answer()
    try:
        await callback.message.edit_text(render_strip(asked_for), reply_markup=build_strip_keyboard(asked_for))
    except TelegramBadRequest as error:
        # a bot may edit its own message for 48 hours only; past that the strip still obeyed, so say so
        if "message is not modified" not in str(error):
            await callback.message.answer(LIGHT_STRIP_CARD_EXPIRED)
