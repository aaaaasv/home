"""What one tracked object looks like in a private chat, and nothing more than the map actually knows."""
from src.bot.handlers.air_threats.messages import CONFIDENCE_LABELS, GONE_NOTE, INBOUND_NOTE, THREAT_EMOJI
from src.modules.air_threats.domain import ApproachingThreat
from src.modules.air_threats.services.geography import bearing_degrees, compass_point


def render_threat(approaching: ApproachingThreat, latitude: float, longitude: float) -> str:
    """
    One card per track: what it is, where it is relative to us, how soon it could be here, and how much the
    map believes itself.

    the uncertainty is printed beside the distance because a position that is ±25 km wide must not read as a
    point — that is the difference between information and false calm. minutes come from the kind's usual
    speed, never from the map, which gives a course but no speed.
    """
    threat = approaching.threat
    towards_them = bearing_degrees(latitude, longitude, threat.latitude, threat.longitude)

    headline = f"{THREAT_EMOJI[threat.kind]} <b>{threat.title}</b>"
    if approaching.is_inbound:
        headline += f" — {INBOUND_NOTE}"

    place = f"{compass_point(towards_them)}, {approaching.distance_kilometres:.0f} км"
    if threat.uncertainty_kilometres:
        place += f" (±{threat.uncertainty_kilometres:.0f} км)"
    if threat.locality:
        place += f" · біля {threat.locality}"

    lines = [headline, place]
    if approaching.is_inbound and approaching.minutes_away is not None:
        lines.append(f"підліт ~{render_minutes(approaching.minutes_away)}")

    trust = CONFIDENCE_LABELS[threat.confidence]
    if threat.source_count:
        trust += f", підтверджень {threat.source_count}"
    if threat.is_position_confirmed:
        trust += ", позиція підтверджена"
    lines.append(f"<i>{trust}</i>")

    return "\n".join(lines)


def render_minutes(minutes: float) -> str:
    """Under two minutes the number of seconds is what matters; above it, whole minutes are enough."""
    if minutes < 2:
        return f"{minutes * 60:.0f} с"
    return f"{minutes:.0f} хв"


def render_gone(previous_text: str) -> str:
    """The card stays where it was, marked — a disappearing message would erase the fact that it had been there."""
    return f"{previous_text}\n\n<b>{GONE_NOTE}</b>"
