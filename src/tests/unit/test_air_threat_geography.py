import unittest

from src.modules.air_threats.services.geography import (
    angle_between_degrees,
    bearing_degrees,
    compass_point,
    distance_kilometres,
)

KYIV_LATITUDE = 50.45
KYIV_LONGITUDE = 30.52
KHARKIV_LATITUDE = 49.99
KHARKIV_LONGITUDE = 36.23


class GeographyTestCase(unittest.TestCase):
    """
    The one part of this module that must be provably right: a wrong bearing turns «летить геть» into «летить сюди».
    """

    def test_distance_between_kyiv_and_kharkiv_matches_the_known_figure(self):
        distance = distance_kilometres(KYIV_LATITUDE, KYIV_LONGITUDE, KHARKIV_LATITUDE, KHARKIV_LONGITUDE)

        self.assertEqual(round(distance), 409)

    def test_distance_from_a_point_to_itself_is_zero(self):
        distance = distance_kilometres(KYIV_LATITUDE, KYIV_LONGITUDE, KYIV_LATITUDE, KYIV_LONGITUDE)

        self.assertEqual(distance, 0.0)

    def test_bearing_from_kharkiv_to_kyiv_points_north_west(self):
        bearing = bearing_degrees(KHARKIV_LATITUDE, KHARKIV_LONGITUDE, KYIV_LATITUDE, KYIV_LONGITUDE)

        self.assertEqual(round(bearing), 279)

    def test_bearing_due_north_is_zero(self):
        bearing = bearing_degrees(KYIV_LATITUDE, KYIV_LONGITUDE, KYIV_LATITUDE + 1, KYIV_LONGITUDE)

        self.assertEqual(round(bearing), 0)

    def test_bearing_due_east_is_ninety(self):
        bearing = bearing_degrees(KYIV_LATITUDE, KYIV_LONGITUDE, KYIV_LATITUDE, KYIV_LONGITUDE + 1)

        self.assertEqual(round(bearing), 90)

    def test_angle_between_bearings_takes_the_shorter_way_round(self):
        self.assertEqual(angle_between_degrees(350.0, 10.0), 20.0)

    def test_angle_between_bearings_never_exceeds_a_half_turn(self):
        self.assertEqual(angle_between_degrees(0.0, 200.0), 160.0)

    def test_angle_between_identical_bearings_is_zero(self):
        self.assertEqual(angle_between_degrees(137.0, 137.0), 0.0)

    def test_compass_point_names_the_direction_a_person_would_say(self):
        named = [compass_point(bearing) for bearing in (0, 45, 90, 135, 180, 225, 270, 315, 359)]

        self.assertEqual(
            named,
            [
                "півночі",
                "північного сходу",
                "сходу",
                "південного сходу",
                "півдня",
                "південного заходу",
                "заходу",
                "північного заходу",
                "півночі",
            ],
        )
