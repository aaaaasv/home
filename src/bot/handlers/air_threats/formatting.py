"""What one tracked object looks like in a private chat, and nothing more than the map actually knows."""
from src.bot.handlers.air_threats.messages import CONFIDENCE_LABELS, GONE_NOTE, INBOUND_NOTE, SOURCE_NOTE, THREAT_EMOJI
from src.modules.air_threats.domain import ApproachingThreat
from src.modules.air_threats.services.geography import bearing_degrees, compass_point


def render_threat(approaching: ApproachingThreat, latitude: float, longitude: float) -> str:
    """
    One card per track: what it is, where it is relative to us, and how much the map believes itself.

    the distance is rounded to whole kilometres and the uncertainty is printed beside it, because a position
    that is ±25 km wide must not be read as a point — that is the difference between information and false calm.
    """
    threat = approaching.threat
    emoji = THREAT_EMOJI[threat.kind]
    towards_them = bearing_degrees(latitude, longitude, threat.latitude, threat.longitude)

    headline = f"{emoji} <b>{threat.title}</b>"
    if approaching.is_inbound:
        headline += f" — {INBOUND_NOTE}"

    place = f"{compass_point(towards_them)}, {approaching.distance_kilometres:.0f} км"
    if threat.locality:
        place += f" · біля {threat.locality}"
    if threat.uncertainty_kilometres:
        place += f" (±{threat.uncertainty_kilometres:.0f} км)"

    trust = CONFIDENCE_LABELS[threat.confidence]
    if threat.source_count:
        trust += f", підтверджень {threat.source_count}"
    if threat.is_position_confirmed:
        trust += ", позиція підтверджена"

    return f"{headline}\n{place}\n<i>{trust}</i>\n\n<i>{SOURCE_NOTE}</i>"


def render_gone(previous_text: str) -> str:
    """The card stays where it was, marked — a disappearing message would erase the fact that it had been there."""
    return f"{previous_text}\n\n<b>{GONE_NOTE}</b>"
