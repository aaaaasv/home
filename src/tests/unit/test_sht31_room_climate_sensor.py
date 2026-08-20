import unittest

from src.infrastructure.adapters.sht31_room_climate_sensor import Sht31RoomClimateSensor


class Sht31ChecksumTestCase(unittest.TestCase):
    def setUp(self):
        self.sensor = Sht31RoomClimateSensor(bus_number=1, address=0x44)

    def test_checksum_matches_the_self_test_from_the_datasheet(self):
        self.assertEqual(self.sensor._checksum(bytes([0xBE, 0xEF])), 0x92)

    def test_a_payload_with_both_checksums_intact_is_accepted(self):
        payload = bytes([0xBE, 0xEF, 0x92, 0xBE, 0xEF, 0x92])

        self.assertTrue(self.sensor._is_payload_intact(payload))

    def test_a_payload_with_one_flipped_bit_is_rejected(self):
        payload = bytes([0xBE, 0xEE, 0x92, 0xBE, 0xEF, 0x92])

        self.assertFalse(self.sensor._is_payload_intact(payload))

    def test_a_payload_of_zeroes_from_a_dead_wire_is_rejected(self):
        payload = bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x00])

        self.assertFalse(self.sensor._is_payload_intact(payload))


class Sht31ConversionTestCase(unittest.TestCase):
    def test_the_raw_ticks_convert_to_the_values_the_datasheet_promises(self):
        # the datasheet's own worked example: both words at mid scale
        temperature_ticks, humidity_ticks = 0x6666, 0x6666

        temperature = -45.0 + 175.0 * temperature_ticks / 65535.0
        humidity = 100.0 * humidity_ticks / 65535.0

        self.assertAlmostEqual(temperature, 25.0, places=1)
        self.assertAlmostEqual(humidity, 40.0, places=1)
