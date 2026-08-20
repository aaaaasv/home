import unittest

from src.modules.weather.domain import VentilationEffect
from src.modules.weather.services.ventilation import absolute_humidity, resolve_ventilation_effect


class AbsoluteHumidityTestCase(unittest.TestCase):
    def test_absolute_humidity_of_cold_saturated_air_is_lower_than_warm_dry_air(self):
        damp_winter_air = absolute_humidity(0.0, 90.0)
        dry_summer_air = absolute_humidity(30.0, 40.0)

        self.assertLess(damp_winter_air, dry_summer_air)

    def test_absolute_humidity_matches_the_published_reference_value(self):
        # textbooks put 20 °C at 50% near 8.65 g/m³; magnus coefficient variants move the last digit, so allow 0.1
        self.assertAlmostEqual(absolute_humidity(20.0, 50.0), 8.65, delta=0.1)


class ResolveVentilationEffectTestCase(unittest.TestCase):
    def test_resolve_ventilation_effect_in_a_dry_heated_flat_stays_silent(self):
        # january: outdoor air reads 90% but carries barely any water, so the difference is too small to report
        effect = resolve_ventilation_effect(
            indoor_temperature_celsius=22.0,
            indoor_humidity_percent=35.0,
            outdoor_temperature_celsius=0.0,
            outdoor_humidity_percent=90.0,
        )

        self.assertIsNone(effect)

    def test_resolve_ventilation_effect_with_much_wetter_air_outside_reports_wetter(self):
        # measured on 2026-07-20 while the air conditioner was drying the flat
        effect = resolve_ventilation_effect(
            indoor_temperature_celsius=24.93,
            indoor_humidity_percent=54.3,
            outdoor_temperature_celsius=24.0,
            outdoor_humidity_percent=74.0,
        )

        self.assertEqual(effect, VentilationEffect.WETTER)

    def test_resolve_ventilation_effect_with_drier_cooler_air_outside_reports_drier(self):
        effect = resolve_ventilation_effect(
            indoor_temperature_celsius=24.0,
            indoor_humidity_percent=70.0,
            outdoor_temperature_celsius=18.0,
            outdoor_humidity_percent=40.0,
        )

        self.assertEqual(effect, VentilationEffect.DRIER)

    def test_resolve_ventilation_effect_with_drier_but_much_hotter_air_outside_stays_silent(self):
        # drier outside, but 9 degrees warmer — opening up would dry the flat only by baking it, so say nothing
        effect = resolve_ventilation_effect(
            indoor_temperature_celsius=24.0,
            indoor_humidity_percent=70.0,
            outdoor_temperature_celsius=33.0,
            outdoor_humidity_percent=20.0,
        )

        self.assertIsNone(effect)

    def test_resolve_ventilation_effect_with_a_small_difference_stays_silent(self):
        effect = resolve_ventilation_effect(
            indoor_temperature_celsius=22.0,
            indoor_humidity_percent=50.0,
            outdoor_temperature_celsius=21.0,
            outdoor_humidity_percent=52.0,
        )

        self.assertIsNone(effect)
