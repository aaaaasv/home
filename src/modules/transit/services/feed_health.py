from datetime import datetime, timedelta

from src.modules.transit.domain import RealtimeSnapshot

# the feed header must be recent — a stale header means the host stopped updating
FEED_TIMESTAMP_STALE_SECONDS = 120
# the freshest vehicle in the whole fleet must be recent — normal pings are 1-4 min apart, so judge the aggregate
FLEET_STALE_SECONDS = 180
# a healthy Kyiv feed carries ~460 vehicles; a collapse to a handful means the feed is broken
MINIMUM_FLEET_SIZE = 50


def is_feed_trustworthy(snapshot: RealtimeSnapshot | None, now: datetime) -> bool:
    """Aggregate-only trust — never flag on one stale vehicle, only on the whole feed going dark"""
    if snapshot is None:
        return False
    if now - snapshot.feed_timestamp > timedelta(seconds=FEED_TIMESTAMP_STALE_SECONDS):
        return False
    if snapshot.total_vehicle_count < MINIMUM_FLEET_SIZE:
        return False
    if snapshot.latest_vehicle_recorded_at is None:
        return False
    if now - snapshot.latest_vehicle_recorded_at > timedelta(seconds=FLEET_STALE_SECONDS):
        return False
    return True
