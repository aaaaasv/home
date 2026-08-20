import unittest

from src.modules.transit.domain import GeoPoint
from src.modules.transit.services.geometry import cumulative_distances, haversine_meters, project_onto_polyline

# a straight meridian polyline at longitude 30.0 — each 0.001° latitude step is ~111.19 m
POINT_ONE = GeoPoint(latitude=50.000, longitude=30.0)
POINT_TWO = GeoPoint(latitude=50.001, longitude=30.0)
POINT_THREE = GeoPoint(latitude=50.002, longitude=30.0)
POLYLINE = [POINT_ONE, POINT_TWO, POINT_THREE]


class HaversineMetersTestCase(unittest.TestCase):
    def test_haversine_between_identical_points_is_zero(self):
        distance = haversine_meters(POINT_ONE, POINT_ONE)

        self.assertEqual(distance, 0.0)

    def test_haversine_over_one_thousandth_degree_latitude_is_about_111_meters(self):
        distance = haversine_meters(POINT_ONE, POINT_TWO)

        self.assertAlmostEqual(distance, 111.19, delta=0.5)


class CumulativeDistancesTestCase(unittest.TestCase):
    def test_cumulative_distances_accumulates_each_segment(self):
        cumulative = cumulative_distances(POLYLINE)

        self.assertEqual(len(cumulative), 3)
        self.assertEqual(cumulative[0], 0.0)
        self.assertAlmostEqual(cumulative[1], 111.19, delta=0.5)
        self.assertAlmostEqual(cumulative[2], 222.39, delta=1.0)


class ProjectOntoPolylineTestCase(unittest.TestCase):
    def setUp(self):
        self.cumulative = cumulative_distances(POLYLINE)

    def test_project_point_on_the_line_has_zero_offset_and_measures_distance_along(self):
        midpoint_of_second_segment = GeoPoint(latitude=50.0015, longitude=30.0)

        projection = project_onto_polyline(midpoint_of_second_segment, POLYLINE, self.cumulative)

        self.assertAlmostEqual(projection.offset_meters, 0.0, delta=0.5)
        self.assertAlmostEqual(projection.distance_along_meters, 166.79, delta=1.0)

    def test_project_point_beside_a_vertex_offsets_by_the_perpendicular_distance(self):
        east_of_second_point = GeoPoint(latitude=50.001, longitude=30.001)

        projection = project_onto_polyline(east_of_second_point, POLYLINE, self.cumulative)

        self.assertAlmostEqual(projection.offset_meters, 71.5, delta=1.0)
        self.assertAlmostEqual(projection.distance_along_meters, 111.19, delta=1.0)


if __name__ == "__main__":
    unittest.main()
