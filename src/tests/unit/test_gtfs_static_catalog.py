import io
import unittest
import zipfile
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from src.infrastructure.adapters.gtfs_static_shape_catalog import (
    GtfsStaticShapeCatalog,
    read_shape_points_by_id,
    select_shapes_serving_stop,
)
from src.modules.transit.domain import GeoPoint

STOP = GeoPoint(latitude=50.0368, longitude=30.0907)
DESTINATION = GeoPoint(latitude=50.0389, longitude=30.1219)
WATCHED_ROUTE_IDS = frozenset({"2_30", "3_127", "2_842", "4_400"})

# route 2_30 runs two directions past the stop: sh_30_center ends at the destination, sh_30_outbound heads away
# route 3_127 (the bus 69) shares the physical stop but has its own stop id, so only its geometry finds it here
# route 4_400's line never comes near the stop; route 2_842 (9К) has no trip and no shape at all
TRIPS_TEXT = (
    "route_id,service_id,trip_id,shape_id\n"
    "2_30,weekday,t_a,sh_30_center\n"
    "2_30,weekday,t_b,sh_30_outbound\n"
    "3_127,weekday,t_c,sh_69_center\n"
    "4_400,weekday,t_d,sh_far\n"
)
# sh_30_center's rows are deliberately out of sequence order so the parser's sort is exercised
SHAPES_TEXT = (
    "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n"
    "sh_30_center,50.038,30.1,2\n"
    "sh_30_center,50.0368,30.0908,1\n"
    "sh_30_center,50.0389,30.1219,3\n"
    "sh_30_outbound,50.0368,30.0908,1\n"
    "sh_30_outbound,50.03,30.08,2\n"
    "sh_30_outbound,50.025,30.07,3\n"
    "sh_69_center,50.0368,30.091,1\n"
    "sh_69_center,50.038,30.11,2\n"
    "sh_69_center,50.0389,30.1219,3\n"
    "sh_far,50.1,30.2,1\n"
    "sh_far,50.11,30.21,2\n"
)

SH_30_CENTER_POINTS = [
    GeoPoint(latitude=50.0368, longitude=30.0908),
    GeoPoint(latitude=50.038, longitude=30.1),
    GeoPoint(latitude=50.0389, longitude=30.1219),
]


def build_static_zip(path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("trips.txt", TRIPS_TEXT)
        archive.writestr("shapes.txt", SHAPES_TEXT)
    path.write_bytes(buffer.getvalue())


class SelectShapesServingStopTestCase(unittest.TestCase):
    def test_select_shapes_picks_the_toward_centre_direction_that_passes_the_stop(self):
        selected = select_shapes_serving_stop(TRIPS_TEXT, SHAPES_TEXT, WATCHED_ROUTE_IDS, STOP, DESTINATION)

        self.assertEqual(set(selected), {"2_30", "3_127"})
        self.assertEqual(selected["2_30"].points, SH_30_CENTER_POINTS)

    def test_select_shapes_omits_a_route_whose_line_never_reaches_the_stop(self):
        selected = select_shapes_serving_stop(TRIPS_TEXT, SHAPES_TEXT, WATCHED_ROUTE_IDS, STOP, DESTINATION)

        self.assertNotIn("4_400", selected)

    def test_select_shapes_omits_a_route_absent_from_the_static_feed(self):
        selected = select_shapes_serving_stop(TRIPS_TEXT, SHAPES_TEXT, WATCHED_ROUTE_IDS, STOP, DESTINATION)

        self.assertNotIn("2_842", selected)


class ReadShapePointsByIdTestCase(unittest.TestCase):
    def test_read_shape_points_by_id_orders_each_shape_by_sequence(self):
        points_by_shape = read_shape_points_by_id(SHAPES_TEXT, {"sh_30_center"})

        self.assertEqual(points_by_shape, {"sh_30_center": SH_30_CENTER_POINTS})


class GtfsStaticShapeCatalogTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._directory = TemporaryDirectory()
        cache_path = Path(self._directory.name) / "gtfs-static.zip"
        build_static_zip(cache_path)
        self.catalog = GtfsStaticShapeCatalog(
            url="http://example.invalid/export-gtfs-static",
            cache_path=cache_path,
            stop=STOP,
            destination=DESTINATION,
            watched_route_ids=WATCHED_ROUTE_IDS,
            refresh_after=timedelta(days=7),
        )

    async def asyncTearDown(self):
        self._directory.cleanup()

    async def test_shape_for_route_returns_the_toward_centre_shape_from_the_cache(self):
        shape = await self.catalog.shape_for_route("2_30")

        self.assertEqual(shape.route_id, "2_30")
        self.assertEqual(shape.points, SH_30_CENTER_POINTS)

    async def test_shape_for_route_returns_none_for_a_route_absent_from_the_static_feed(self):
        shape = await self.catalog.shape_for_route("2_842")

        self.assertIsNone(shape)


if __name__ == "__main__":
    unittest.main()
