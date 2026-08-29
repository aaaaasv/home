import unittest
from datetime import datetime, timezone

from src.bot.handlers.power.formatting import render_mains_change
from src.modules.power.domain import EcoFlowState, GridState
from src.modules.power.mains_monitor import MainsMonitor, classify_grid


def build_state(**overrides) -> EcoFlowState:
    defaults = dict(
        battery_percent=82.0,
        on_mains=True,
        ac_input_power=310,
        ac_output_power=90,
        ac_output_on=True,
        usb_output_on=False,
        dc_output_on=False,
        remaining_minutes=95,
        charge_limit_max=80,
        backup_reserve_percent=None,
        cell_temperature_celsius=27,
        as_of=datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return EcoFlowState(**defaults)


def on_grid(**overrides) -> EcoFlowState:
    return build_state(ac_input_power=310, ac_output_power=90, **overrides)


def on_battery(**overrides) -> EcoFlowState:
    return build_state(ac_input_power=0, ac_output_power=90, on_mains=False, **overrides)


def idle_and_full(**overrides) -> EcoFlowState:
    """Sitting on mains at its charge limit with nothing plugged in — draws nothing, feeds nothing."""
    return build_state(ac_input_power=0, ac_output_power=0, on_mains=False, **overrides)


class ClassifyGridTestCase(unittest.TestCase):
    """
    The Delta 2 reports watts, never a "plugged in" flag, so the grid has to be inferred from them.

    the whole point of the third answer is the idle full station: it draws nothing, exactly like a station
    running on battery, and telling those apart wrongly is a false blackout alert at three in the morning.
    """

    def test_a_station_drawing_from_the_wall_is_on_the_grid(self):
        grid = classify_grid(on_grid())

        self.assertEqual(grid, GridState.ON_GRID)

    def test_a_station_feeding_the_flat_while_drawing_nothing_is_on_battery(self):
        grid = classify_grid(on_battery())

        self.assertEqual(grid, GridState.ON_BATTERY)

    def test_a_station_idle_and_full_on_mains_is_unknown_rather_than_a_blackout(self):
        grid = classify_grid(idle_and_full())

        self.assertEqual(grid, GridState.UNKNOWN)

    def test_an_unreachable_station_is_unknown(self):
        grid = classify_grid(None)

        self.assertEqual(grid, GridState.UNKNOWN)


class MainsMonitorTestCase(unittest.TestCase):
    """
    The two messages the whole of layer 1 exists to send, and every way they could be sent wrongly.

    the message pings the family, so a blip, a restart or an unreachable station must all stay silent.
    """

    def test_the_first_known_reading_establishes_the_state_without_announcing_it(self):
        monitor = MainsMonitor()

        announcements = [monitor.update(on_grid()), monitor.update(on_grid()), monitor.update(on_grid())]

        self.assertEqual(announcements, [None, None, None])

    def test_losing_the_grid_is_announced_once_it_has_been_seen_twice(self):
        monitor = MainsMonitor()
        monitor.update(on_grid())
        monitor.update(on_grid())

        announcements = [monitor.update(on_battery()), monitor.update(on_battery()), monitor.update(on_battery())]

        self.assertEqual(announcements, [None, GridState.ON_BATTERY, None])

    def test_the_grid_returning_is_announced_the_same_way(self):
        monitor = MainsMonitor()
        for state in (on_grid(), on_grid(), on_battery(), on_battery()):
            monitor.update(state)

        announcements = [monitor.update(on_grid()), monitor.update(on_grid())]

        self.assertEqual(announcements, [None, GridState.ON_GRID])

    def test_a_single_reading_off_the_grid_that_recovers_announces_nothing(self):
        monitor = MainsMonitor()
        monitor.update(on_grid())
        monitor.update(on_grid())

        announcements = [monitor.update(on_battery()), monitor.update(on_grid()), monitor.update(on_grid())]

        self.assertEqual(announcements, [None, None, None])

    def test_an_unreachable_station_never_announces_a_blackout(self):
        monitor = MainsMonitor()
        monitor.update(on_grid())
        monitor.update(on_grid())

        announcements = [monitor.update(None), monitor.update(None), monitor.update(None)]

        self.assertEqual(announcements, [None, None, None])

    def test_a_station_going_idle_and_full_never_announces_a_blackout(self):
        monitor = MainsMonitor()
        monitor.update(on_grid())
        monitor.update(on_grid())

        announcements = [monitor.update(idle_and_full()), monitor.update(idle_and_full())]

        self.assertEqual(announcements, [None, None])

    def test_an_outage_that_starts_while_the_station_is_unreachable_is_still_announced_on_return(self):
        monitor = MainsMonitor()
        monitor.update(on_grid())
        monitor.update(on_grid())
        monitor.update(None)

        announcements = [monitor.update(on_battery()), monitor.update(on_battery())]

        self.assertEqual(announcements, [None, GridState.ON_BATTERY])

    def test_a_restart_during_an_outage_does_not_announce_the_outage_it_woke_up_inside(self):
        monitor = MainsMonitor()

        announcements = [monitor.update(on_battery()), monitor.update(on_battery()), monitor.update(on_battery())]

        self.assertEqual(announcements, [None, None, None])

    def test_a_restart_during_an_outage_still_announces_the_grid_coming_back(self):
        monitor = MainsMonitor()
        monitor.update(on_battery())
        monitor.update(on_battery())

        announcements = [monitor.update(on_grid()), monitor.update(on_grid())]

        self.assertEqual(announcements, [None, GridState.ON_GRID])


class RenderMainsChangeTestCase(unittest.TestCase):
    def test_losing_the_grid_reports_the_charge_and_how_long_it_holds(self):
        text = render_mains_change(GridState.ON_BATTERY, on_battery(battery_percent=82.0, remaining_minutes=95))

        self.assertEqual(text, "🕯 <b>Світло зникло</b>\n\nDelta 2 тримає квартиру — 82%, лишилось ~1 год 35 хв")

    def test_losing_the_grid_without_an_estimate_still_reports_the_charge(self):
        text = render_mains_change(GridState.ON_BATTERY, on_battery(battery_percent=82.0, remaining_minutes=None))

        self.assertEqual(text, "🕯 <b>Світло зникло</b>\n\nDelta 2 тримає квартиру — 82%")

    def test_the_grid_returning_reports_the_charge_and_that_it_is_filling_again(self):
        text = render_mains_change(GridState.ON_GRID, on_grid(battery_percent=61.0))

        self.assertEqual(text, "💡 <b>Світло є</b>\n\nDelta 2 — 61%, заряджається")
