"""The strip as one line: what it is doing, and nothing else."""
from src.bot.handlers.lighting.messages import LIGHT_STRIP_OFF, LIGHT_STRIP_ON
from src.modules.lighting.domain import PanelLightState


def render_strip(state: PanelLightState) -> str:
    """Where the strip stands, rounded to a whole percent — nobody taps a slider to a decimal."""
    if not state.is_on:
        return LIGHT_STRIP_OFF
    return LIGHT_STRIP_ON.format(percent=round(state.brightness_percent))
