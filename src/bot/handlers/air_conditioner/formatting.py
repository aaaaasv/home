"""How the air conditioner card renders."""
from datetime import datetime

from src.bot.handlers.air_conditioner.messages import (
    AIR_CONDITIONER_BADGE_QUIET,
    AIR_CONDITIONER_BADGE_TURBO,
    AIR_CONDITIONER_BADGE_XFAN,
    AIR_CONDITIONER_LONG_RUN,
    AIR_CONDITIONER_LONG_RUN_WITH_ROOM,
    AIR_CONDITIONER_OPEN_WINDOWS_INSTEAD,
    AIR_CONDITIONER_ROOM_TEMPERATURE,
    AIR_CONDITIONER_ROOM_TEMPERATURE_WITH_HUMIDITY,
    AIR_CONDITIONER_STATE_LINES,
    AIR_CONDITIONER_STATE_OFF,
    AIR_CONDITIONER_TITLE,
    AIR_CONDITIONER_UPDATED_AT,
)
from src.modules.air_conditioner.domain import AirConditionerRuntimeNotice, AirConditionerState
from src.modules.room_climate.domain import RoomClimate
from src.modules.weather.domain import VentilationEffect


def render_air_conditioner(
    state: AirConditionerState,
    room: str,
    moment: datetime,
    indoor: RoomClimate | None = None,
    ventilation: VentilationEffect | None = None,
) -> str:
    lines = [AIR_CONDITIONER_TITLE.format(room=room), ""]
    if state.is_on:
        lines.append(AIR_CONDITIONER_STATE_LINES[state.mode].format(target=state.target_temperature_celsius))
    else:
        lines.append(AIR_CONDITIONER_STATE_OFF.format(target=state.target_temperature_celsius))

    badges = _render_air_conditioner_badges(state)
    if badges:
        lines.append(badges)

    room_line = _render_room_line(state, indoor)
    if room_line:
        lines.append(room_line)

    # only when opening up would actually beat running the compressor — otherwise the card stays out of the way
    if ventilation == VentilationEffect.DRIER:
        lines.append(AIR_CONDITIONER_OPEN_WINDOWS_INSTEAD)

    lines.extend(["", AIR_CONDITIONER_UPDATED_AT.format(time=f"{moment:%H:%M}")])
    return "\n".join(lines)


def _render_air_conditioner_badges(state: AirConditionerState) -> str | None:
    # a switched-off unit is not turboing anything, so its stale flags stay off the card
    if not state.is_on:
        return None
    badges = []
    if state.turbo:
        badges.append(AIR_CONDITIONER_BADGE_TURBO)
    if state.quiet:
        badges.append(AIR_CONDITIONER_BADGE_QUIET)
    if state.xfan:
        badges.append(AIR_CONDITIONER_BADGE_XFAN)
    return " · ".join(badges) if badges else None


def _render_room_line(state: AirConditionerState, indoor: RoomClimate | None) -> str | None:
    # prefer our own sensor: the unit's is mounted high on the wall and reports no humidity at all
    if indoor is not None:
        return AIR_CONDITIONER_ROOM_TEMPERATURE_WITH_HUMIDITY.format(
            temperature=f"{indoor.temperature_celsius:.0f}", humidity=f"{indoor.relative_humidity_percent:.0f}"
        )
    if state.room_temperature_celsius is not None:
        return AIR_CONDITIONER_ROOM_TEMPERATURE.format(temperature=state.room_temperature_celsius)
    return None


def render_air_conditioner_long_run(notice: AirConditionerRuntimeNotice) -> str:
    if notice.room_temperature_celsius is None:
        return AIR_CONDITIONER_LONG_RUN.format(hours=notice.hours)
    return AIR_CONDITIONER_LONG_RUN_WITH_ROOM.format(hours=notice.hours, temperature=notice.room_temperature_celsius)
