import asyncio
import csv
import io
import logging
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiohttp

from src.common.time import current_time
from src.modules.transit.domain import GeoPoint, RouteShape
from src.modules.transit.services.geometry import cumulative_distances, haversine_meters, project_onto_polyline

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 60
TRIPS_FILE = "trips.txt"
SHAPES_FILE = "shapes.txt"
# a shape counts as serving the stop if its line passes within this of the stop coordinate — wide enough for a
# stop set back from the kerb (and for both carriageways of one street), tight enough to exclude a parallel street
STOP_SHAPE_MATCH_METERS = 60.0


class GtfsStaticShapeCatalog:
    """Serves route geometry from a slow host's zip, cached on disk and parsed lazily so a render never blocks"""

    def __init__(
        self,
        url: str,
        cache_path: Path,
        stop: GeoPoint,
        destination: GeoPoint,
        watched_route_ids: frozenset[str],
        refresh_after: timedelta,
    ):
        self.url = url
        self.cache_path = cache_path
        self.stop = stop
        self.destination = destination
        self.watched_route_ids = watched_route_ids
        self.refresh_after = refresh_after
        self._shapes_by_route: dict[str, RouteShape] | None = None

    async def refresh(self) -> None:
        if self._cache_is_fresh():
            return
        payload = await self._download()
        if payload is None:
            # keep serving the stale cache — week-old geometry is still geometry, a flaky host is not an outage
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_bytes(payload)
        self._shapes_by_route = None

    async def shape_for_route(self, route_id: str) -> RouteShape | None:
        if self._shapes_by_route is None:
            self._shapes_by_route = self._parse_cached_shapes()
        return self._shapes_by_route.get(route_id)

    def _cache_is_fresh(self) -> bool:
        if not self.cache_path.exists():
            return False
        modified_at = datetime.fromtimestamp(self.cache_path.stat().st_mtime, tz=timezone.utc)
        return current_time() - modified_at < self.refresh_after

    async def _download(self) -> bytes | None:
        try:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.url) as response:
                    response.raise_for_status()
                    return await response.read()
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            logger.warning("Transit static catalog fetch failed: %r", error)
            return None

    def _parse_cached_shapes(self) -> dict[str, RouteShape]:
        if not self.cache_path.exists():
            return {}
        with zipfile.ZipFile(self.cache_path) as archive:
            trips_text = archive.read(TRIPS_FILE).decode("utf-8-sig")
            shapes_text = archive.read(SHAPES_FILE).decode("utf-8-sig")
        return select_shapes_serving_stop(trips_text, shapes_text, self.watched_route_ids, self.stop, self.destination)


def select_shapes_serving_stop(
    trips_text: str,
    shapes_text: str,
    watched_route_ids: frozenset[str],
    stop: GeoPoint,
    destination: GeoPoint,
) -> dict[str, RouteShape]:
    """
    Per watched route, the shape whose line passes the stop and heads to the centre — chosen by geometry, not by
    stop_times. the static stop_times list only a few major stops, and each mode gets its own stop id, so a bus and
    a trolleybus sharing one physical stop never share one; matching the stop coordinate against the line is robust
    to both. of a route's directions that pass the stop, the toward-centre one is the shape ending nearest the
    shared destination
    """
    shape_ids_by_route: dict[str, set[str]] = defaultdict(set)
    for row in csv.DictReader(io.StringIO(trips_text)):
        route_id = row["route_id"]
        shape_id = row.get("shape_id")
        if route_id in watched_route_ids and shape_id:
            shape_ids_by_route[route_id].add(shape_id)

    wanted_shape_ids = {shape_id for shape_ids in shape_ids_by_route.values() for shape_id in shape_ids}
    points_by_shape = read_shape_points_by_id(shapes_text, wanted_shape_ids)

    shapes_by_route: dict[str, RouteShape] = {}
    for route_id, shape_ids in shape_ids_by_route.items():
        points = _choose_shape_toward_stop(shape_ids, points_by_shape, stop, destination)
        if points is not None:
            shapes_by_route[route_id] = RouteShape(route_id=route_id, points=points)
    return shapes_by_route


def read_shape_points_by_id(shapes_text: str, wanted_shape_ids: set[str]) -> dict[str, list[GeoPoint]]:
    """Every wanted shape's polyline, ordered by point sequence, in one pass over shapes.txt"""
    rows_by_shape: dict[str, list[dict]] = defaultdict(list)
    for row in csv.DictReader(io.StringIO(shapes_text)):
        if row["shape_id"] in wanted_shape_ids:
            rows_by_shape[row["shape_id"]].append(row)

    points_by_shape: dict[str, list[GeoPoint]] = {}
    for shape_id, rows in rows_by_shape.items():
        rows.sort(key=lambda row: int(row["shape_pt_sequence"]))
        points_by_shape[shape_id] = [
            GeoPoint(latitude=float(row["shape_pt_lat"]), longitude=float(row["shape_pt_lon"])) for row in rows
        ]
    return points_by_shape


def _choose_shape_toward_stop(
    shape_ids: set[str],
    points_by_shape: dict[str, list[GeoPoint]],
    stop: GeoPoint,
    destination: GeoPoint,
) -> list[GeoPoint] | None:
    candidates = []
    for shape_id in shape_ids:
        points = points_by_shape.get(shape_id)
        if points is None or len(points) < 2:
            continue
        stop_offset = project_onto_polyline(stop, points, cumulative_distances(points)).offset_meters
        if stop_offset > STOP_SHAPE_MATCH_METERS:
            continue
        endpoint_to_destination = haversine_meters(points[-1], destination)
        candidates.append((endpoint_to_destination, stop_offset, points))
    if not candidates:
        return None
    # the toward-centre shape ends nearest the destination; ties break to the one passing the stop closest
    candidates.sort(key=lambda candidate: (candidate[0], candidate[1]))
    return candidates[0][2]
