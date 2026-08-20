import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Protocol

import aiohttp
from google.transit import gtfs_realtime_pb2

from src.common.time import current_time
from src.modules.transit.domain import GeoPoint, RealtimeSnapshot, VehiclePosition

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 15
# the feed refreshes ~every 15 s; a poll younger than this reuses the cached bytes so the host is never hammered
MINIMUM_FETCH_INTERVAL_SECONDS = 15


class RealtimeFeed(Protocol):
    """Fetches live vehicle positions — returns None when the feed cannot be reached"""

    async def fetch(self) -> RealtimeSnapshot | None:
        ...


class GtfsRealtimeFeed:
    """Polls the GTFS-realtime protobuf endpoint, honouring the host's ETag so a 304 costs no re-parse"""

    def __init__(self, url: str, watched_route_ids: frozenset[str]):
        self.url = url
        self.watched_route_ids = watched_route_ids
        self._etag: str | None = None
        self._cached_snapshot: RealtimeSnapshot | None = None
        self._last_fetched_at: datetime | None = None

    async def fetch(self) -> RealtimeSnapshot | None:
        now = current_time()
        if self._last_fetched_at is not None and now - self._last_fetched_at < timedelta(
            seconds=MINIMUM_FETCH_INTERVAL_SECONDS
        ):
            return self._cached_snapshot
        return await self._fetch_from_network(now)

    async def _fetch_from_network(self, now: datetime) -> RealtimeSnapshot | None:
        self._last_fetched_at = now
        headers = {}
        if self._etag is not None:
            headers["If-None-Match"] = self._etag
        try:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.url, headers=headers) as response:
                    if response.status == 304:
                        return self._refresh_cached_fetched_at(now)
                    response.raise_for_status()
                    payload = await response.read()
                    self._etag = response.headers.get("ETag")
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            logger.warning("Transit realtime fetch failed: %r", error)
            return None

        self._cached_snapshot = parse_realtime_snapshot(payload, self.watched_route_ids, now)
        return self._cached_snapshot

    def _refresh_cached_fetched_at(self, now: datetime) -> RealtimeSnapshot | None:
        # a 304 means the positions are unchanged; keep the old feed_timestamp so a host stuck on 304 stays catchable
        if self._cached_snapshot is None:
            return None
        self._cached_snapshot = self._cached_snapshot.model_copy(update={"fetched_at": now})
        return self._cached_snapshot


def parse_realtime_snapshot(
    payload: bytes, watched_route_ids: frozenset[str], fetched_at: datetime
) -> RealtimeSnapshot:
    """Filter the protobuf to the watched routes while measuring the whole feed's aggregates in one pass"""
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(payload)
    feed_timestamp = datetime.fromtimestamp(feed.header.timestamp, tz=timezone.utc)

    watched_vehicles: list[VehiclePosition] = []
    total_vehicle_count = 0
    latest_vehicle_recorded_at: datetime | None = None
    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue
        vehicle = entity.vehicle
        total_vehicle_count += 1
        recorded_at = (
            datetime.fromtimestamp(vehicle.timestamp, tz=timezone.utc)
            if vehicle.HasField("timestamp")
            else feed_timestamp
        )
        if latest_vehicle_recorded_at is None or recorded_at > latest_vehicle_recorded_at:
            latest_vehicle_recorded_at = recorded_at
        route_id = vehicle.trip.route_id
        if route_id not in watched_route_ids:
            continue
        watched_vehicles.append(
            VehiclePosition(
                vehicle_id=vehicle.vehicle.id,
                route_id=route_id,
                location=GeoPoint(latitude=vehicle.position.latitude, longitude=vehicle.position.longitude),
                recorded_at=recorded_at,
            )
        )

    return RealtimeSnapshot(
        vehicles=watched_vehicles,
        total_vehicle_count=total_vehicle_count,
        latest_vehicle_recorded_at=latest_vehicle_recorded_at,
        feed_timestamp=feed_timestamp,
        fetched_at=fetched_at,
    )
