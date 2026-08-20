"""How the transit arrival card renders."""
from datetime import datetime

from src.bot.handlers.transit.messages import (
    TRANSIT_AIR_RAID,
    TRANSIT_ARRIVAL_DISTANCE,
    TRANSIT_ARRIVAL_ETA,
    TRANSIT_ARRIVAL_INVISIBLE,
    TRANSIT_ARRIVAL_NEAREST,
    TRANSIT_FEED_DOWN,
    TRANSIT_FOOTER_FROZEN,
    TRANSIT_FOOTER_LIVE,
    TRANSIT_NEAREST_PREFIX,
)
from src.modules.transit.domain import RouteArrival, RouteVehicleKind, TransitReport, TransitReportStatus

TRANSIT_VEHICLE_EMOJI = {
    RouteVehicleKind.TROLLEYBUS: "🚎",
    RouteVehicleKind.BUS: "🚌",
}


def render_transit_card(report: TransitReport, generated_at: datetime, is_live: bool) -> str:
    if report.status == TransitReportStatus.AIR_RAID:
        body = TRANSIT_AIR_RAID
    elif report.status == TransitReportStatus.FEED_UNAVAILABLE:
        body = TRANSIT_FEED_DOWN
    else:
        body = _render_transit_arrivals(report.arrivals)
    footer = (TRANSIT_FOOTER_LIVE if is_live else TRANSIT_FOOTER_FROZEN).format(time=generated_at.strftime("%H:%M"))
    return f"{body}\n\n{footer}"


def _render_transit_arrivals(arrivals: list[RouteArrival]) -> str:
    fragments = []
    nearest_shown = False
    for arrival in arrivals:
        is_nearest = arrival.eta_minutes is not None and not nearest_shown
        fragments.append(_render_transit_arrival(arrival, is_nearest))
        nearest_shown = nearest_shown or is_nearest
    return TRANSIT_NEAREST_PREFIX + " · ".join(fragments)


def _render_transit_arrival(arrival: RouteArrival, is_nearest: bool) -> str:
    emoji = TRANSIT_VEHICLE_EMOJI[arrival.route.vehicle_kind]
    route = arrival.route.short_name
    if arrival.eta_minutes is None:
        return TRANSIT_ARRIVAL_INVISIBLE.format(emoji=emoji, route=route)
    if not is_nearest:
        return TRANSIT_ARRIVAL_ETA.format(emoji=emoji, route=route, eta=arrival.eta_minutes)
    # the soonest route gets the fuller line — «за ~N хв» plus its distance when known
    fragment = TRANSIT_ARRIVAL_NEAREST.format(emoji=emoji, route=route, eta=arrival.eta_minutes)
    if arrival.distance_meters is not None:
        fragment += TRANSIT_ARRIVAL_DISTANCE.format(distance=_format_kilometers(arrival.distance_meters))
    return fragment


def _format_kilometers(meters: float) -> str:
    return f"{meters / 1000:.1f}"
