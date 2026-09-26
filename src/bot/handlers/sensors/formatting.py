"""Rendering the flat's own air, which is read at a glance and has to stand on its own.

Two decisions worth keeping. A stale sensor is shown **with its last number struck through** rather than
hidden, because a room quietly missing from the list reads as a room that is fine. And the trend is rendered
only when it is large enough to mean something: a tenth of a degree between two days is the sensor's own
noise, and printing it every morning teaches people to stop reading the line.
"""
from html import escape

from src.bot.handlers.sensors import messages
from src.common.household_calendar import HouseholdCalendar
from src.modules.sensors.domain import ClimateSnapshot, ClimateTrend, SensorNow

# below this a difference is the sensor's own noise rather than anything that happened in the flat
NOTICEABLE_TEMPERATURE_CHANGE = 0.5
NOTICEABLE_HUMIDITY_CHANGE = 3.0
LOW_BATTERY_PERCENT = 20.0


def render_climate_card(
    snapshot: ClimateSnapshot,
    trend: ClimateTrend,
    pot_labels: dict[str, str],
    calendar: HouseholdCalendar,
) -> str:
    if not snapshot.air and not snapshot.soil:
        return messages.CLIMATE_NOTHING_YET

    lines = [messages.CLIMATE_TITLE, ""]
    average = _render_average(snapshot)
    if average:
        lines.extend([average, ""])

    if snapshot.air:
        lines.append(messages.CLIMATE_ROOMS_TITLE)
        lines.extend(_render_air(one) for one in snapshot.air)

    if snapshot.soil:
        lines.extend(["", messages.CLIMATE_POTS_TITLE])
        lines.extend(_render_soil(one, pot_labels.get(one.sensor, one.sensor)) for one in snapshot.soil)

    for line in _render_trend(trend):
        lines.extend(["", line])

    lines.extend(["", f"<i>станом на {calendar.local_time(snapshot.taken_at):%H:%M}</i>"])
    return "\n".join(lines)


def render_pot_line(soil: SensorNow) -> str:
    """The pot's own air and earth, for a plant card that has a probe standing in it."""
    parts = []
    if soil.temperature_celsius is not None:
        parts.append(f"{soil.temperature_celsius:.0f}°")
    if soil.soil_moisture_percent is not None:
        parts.append(f"ґрунт {soil.soil_moisture_percent:.0f}%")
    if soil.relative_humidity_percent is not None:
        parts.append(f"повітря {soil.relative_humidity_percent:.0f}%")
    return f"🌡 у горщику {' · '.join(parts)}" if parts else ""


def render_room_line(room: str, air: SensorNow) -> str:
    """The room's air for a plant with no probe of its own — named, so nobody reads it as the pot's."""
    return f"🌡 у кімнаті «{escape(room)}» {_air_values(air)}"


def _render_average(snapshot: ClimateSnapshot) -> str:
    temperature = snapshot.average_temperature_celsius
    humidity = snapshot.average_humidity_percent
    if temperature is None and humidity is None:
        return ""
    parts = []
    if temperature is not None:
        parts.append(f"{temperature:.1f}°")
    if humidity is not None:
        parts.append(f"{humidity:.0f}%")
    return f"загалом {' · '.join(parts)}"


def _render_air(one: SensorNow) -> str:
    name = escape(one.room or one.sensor)
    values = _air_values(one)
    if one.is_stale:
        return f"· {name} — <s>{values}</s> <i>{messages.CLIMATE_STALE_NOTE}</i>"
    return f"· {name} — {values}{_battery(one)}"


def _render_soil(one: SensorNow, label: str) -> str:
    parts = []
    if one.soil_moisture_percent is not None:
        parts.append(f"ґрунт {one.soil_moisture_percent:.0f}%")
    if one.temperature_celsius is not None:
        parts.append(f"{one.temperature_celsius:.0f}°")
    values = " · ".join(parts) or "—"
    if one.is_stale:
        return f"· {escape(label)} — <s>{values}</s> <i>{messages.CLIMATE_STALE_NOTE}</i>"
    return f"· {escape(label)} — {values}{_battery(one)}"


def _air_values(one: SensorNow) -> str:
    parts = []
    if one.temperature_celsius is not None:
        parts.append(f"{one.temperature_celsius:.1f}°")
    if one.relative_humidity_percent is not None:
        parts.append(f"{one.relative_humidity_percent:.0f}%")
    return " · ".join(parts) or "—"


def _battery(one: SensorNow) -> str:
    if one.battery_percent is None or one.battery_percent > LOW_BATTERY_PERCENT:
        return ""
    return f" · 🔋 {messages.CLIMATE_LOW_BATTERY_NOTE.format(percent=f'{one.battery_percent:.0f}')}"


def render_trend_summary(trend: ClimateTrend) -> str:
    """The single most telling movement, for a digest line that has no room for three."""
    said = _render_trend(trend)
    return said[0] if said else ""


def _render_trend(trend: ClimateTrend) -> list[str]:
    said = []
    for change, span in (
        (trend.temperature_change_since_yesterday, "ніж учора"),
        (trend.temperature_change_since_last_week, "ніж за тиждень"),
    ):
        if change is not None and abs(change) >= NOTICEABLE_TEMPERATURE_CHANGE:
            said.append(f"{_arrow(change)} на {abs(change):.1f}° {'тепліше' if change > 0 else 'холодніше'} {span}")

    humidity = trend.humidity_change_since_last_week
    if humidity is not None and abs(humidity) >= NOTICEABLE_HUMIDITY_CHANGE:
        said.append(
            f"{_arrow(humidity)} на {abs(humidity):.0f}% {'вологіше' if humidity > 0 else 'сухіше'} ніж за тиждень"
        )
    return said


def _arrow(change: float) -> str:
    return "↗" if change > 0 else "↘"
