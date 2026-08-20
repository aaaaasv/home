from collections.abc import Callable
from datetime import datetime

from src.common.time import current_time
from src.modules.transit.domain import TransitReport, TransitReportStatus, WatchedRoute
from src.modules.transit.services.air_raid_alert_source import AirRaidAlertSource
from src.modules.transit.services.arrival_estimator import ArrivalEstimator
from src.modules.transit.services.feed_health import is_feed_trustworthy
from src.modules.transit.services.realtime_feed import RealtimeFeed
from src.modules.transit.services.route_shape_catalog import RouteShapeCatalog


class ComposeTransitReportUseCase:
    """Turns the alert flag, feed health and route geometry into one TransitReport for the card to render"""

    def __init__(
        self,
        realtime_feed: RealtimeFeed,
        shape_catalog: RouteShapeCatalog,
        arrival_estimator: ArrivalEstimator,
        air_raid_alert_source: AirRaidAlertSource,
        watched_routes: tuple[WatchedRoute, ...],
        clock: Callable[[], datetime] = current_time,
    ):
        self.realtime_feed = realtime_feed
        self.shape_catalog = shape_catalog
        self.arrival_estimator = arrival_estimator
        self.air_raid_alert_source = air_raid_alert_source
        self.watched_routes = watched_routes
        self.clock = clock

    async def __call__(self) -> TransitReport:
        # only an explicit alert blanks the card; an unreadable status proceeds — sanity and feed aggregates still guard
        if await self.air_raid_alert_source.is_alert_active() is True:
            return TransitReport(status=TransitReportStatus.AIR_RAID)

        snapshot = await self.realtime_feed.fetch()
        if not is_feed_trustworthy(snapshot, self.clock()):
            return TransitReport(status=TransitReportStatus.FEED_UNAVAILABLE)

        shapes = {
            route.route_id: shape
            for route in self.watched_routes
            if (shape := await self.shape_catalog.shape_for_route(route.route_id))
        }
        arrivals = self.arrival_estimator.estimate(snapshot, shapes)
        return TransitReport(status=TransitReportStatus.ARRIVALS, arrivals=arrivals)
