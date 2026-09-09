import unittest
from datetime import datetime, timezone

from src.bot.handlers.power.formatting import render_mains_change
from src.modules.power.domain import EcoFlowState, GridState, UpsState
from src.modules.power.mains_monitor import MainsMonitor, classify_grid, classify_grid_from_station


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


def hat(mains_present: bool, **overrides) -> UpsState:
    defaults = dict(
        mains_present=mains_present,
        battery_volts=4.17,
        battery_percent=98.0,
        as_of=datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return UpsState(**defaults)


class ClassifyGridFromStationTestCase(unittest.TestCase):
    """
    The Delta 2 reports watts, never a "plugged in" flag, so the grid has to be inferred from them.

    the whole point of the third answer is the idle full station: it draws nothing, exactly like a station
    running on battery, and telling those apart wrongly is a false blackout alert at three in the morning.
    """

    def test_classify_a_station_drawing_from_the_wall_is_on_the_grid(self):
        grid = classify_grid_from_station(on_grid())

        self.assertEqual(grid, GridState.ON_GRID)

    def test_classify_a_station_feeding_the_flat_while_drawing_nothing_is_on_battery(self):
        grid = classify_grid_from_station(on_battery())

        self.assertEqual(grid, GridState.ON_BATTERY)

    def test_classify_a_station_idle_and_full_on_mains_is_unknown_rather_than_a_blackout(self):
        grid = classify_grid_from_station(idle_and_full())

        self.assertEqual(grid, GridState.UNKNOWN)

    def test_classify_an_unreachable_station_is_unknown(self):
        grid = classify_grid_from_station(None)

        self.assertEqual(grid, GridState.UNKNOWN)


class ClassifyGridTestCase(unittest.TestCase):
    """
    The hat's line is wired to the socket, so where it can answer it outranks anything inferred from watts.

    the one case it cannot answer alone is the transfer switch: thrown, it puts the whole flat — this pi
    included — on the station, and the line then reports the station's power as the city's.
    """

    def test_classify_a_hat_seeing_the_socket_alive_is_on_the_grid(self):
        grid = classify_grid(hat(mains_present=True), None)

        self.assertEqual(grid, GridState.ON_GRID)

    def test_classify_a_hat_seeing_the_socket_dead_is_on_battery(self):
        grid = classify_grid(hat(mains_present=False), None)

        self.assertEqual(grid, GridState.ON_BATTERY)

    def test_classify_a_hat_answers_where_an_idle_full_station_could_not(self):
        grid = classify_grid(hat(mains_present=True), idle_and_full())

        self.assertEqual(grid, GridState.ON_GRID)

    def test_classify_a_live_socket_fed_by_the_station_is_still_on_battery(self):
        grid = classify_grid(hat(mains_present=True), on_battery())

        self.assertEqual(grid, GridState.ON_BATTERY)

    def test_classify_a_dead_socket_is_on_battery_even_while_the_station_charges(self):
        grid = classify_grid(hat(mains_present=False), on_grid())

        self.assertEqual(grid, GridState.ON_BATTERY)

    def test_classify_without_a_hat_falls_back_to_the_station(self):
        grid = classify_grid(None, on_battery())

        self.assertEqual(grid, GridState.ON_BATTERY)

    def test_classify_with_neither_source_is_unknown(self):
        grid = classify_grid(None, None)

        self.assertEqual(grid, GridState.UNKNOWN)


class MainsMonitorTestCase(unittest.TestCase):
    """
    The two messages the whole of layer 1 exists to send, and every way they could be sent wrongly.

    the message pings the family, so a blip, a restart or an unreachable station must all stay silent.
    """

    def test_update_the_first_known_reading_establishes_the_state_without_announcing_it(self):
        monitor = MainsMonitor()

        announcements = [monitor.update(None, on_grid()) for _ in range(3)]

        self.assertEqual(announcements, [None, None, None])

    def test_update_losing_the_grid_is_announced_once_it_has_been_seen_twice(self):
        monitor = MainsMonitor()
        monitor.update(None, on_grid())
        monitor.update(None, on_grid())

        announcements = [monitor.update(None, on_battery()) for _ in range(3)]

        self.assertEqual(announcements, [None, GridState.ON_BATTERY, None])

    def test_update_the_grid_returning_is_announced_the_same_way(self):
        monitor = MainsMonitor()
        for state in (on_grid(), on_grid(), on_battery(), on_battery()):
            monitor.update(None, state)

        announcements = [monitor.update(None, on_grid()), monitor.update(None, on_grid())]

        self.assertEqual(announcements, [None, GridState.ON_GRID])

    def test_update_a_single_reading_off_the_grid_that_recovers_announces_nothing(self):
        monitor = MainsMonitor()
        monitor.update(None, on_grid())
        monitor.update(None, on_grid())

        announcements = [
            monitor.update(None, on_battery()),
            monitor.update(None, on_grid()),
            monitor.update(None, on_grid()),
        ]

        self.assertEqual(announcements, [None, None, None])

    def test_update_an_unreachable_station_never_announces_a_blackout(self):
        monitor = MainsMonitor()
        monitor.update(None, on_grid())
        monitor.update(None, on_grid())

        announcements = [monitor.update(None, None) for _ in range(3)]

        self.assertEqual(announcements, [None, None, None])

    def test_update_a_station_going_idle_and_full_never_announces_a_blackout(self):
        monitor = MainsMonitor()
        monitor.update(None, on_grid())
        monitor.update(None, on_grid())

        announcements = [monitor.update(None, idle_and_full()) for _ in range(2)]

        self.assertEqual(announcements, [None, None])

    def test_update_an_outage_that_starts_while_the_station_is_unreachable_is_still_announced_on_return(self):
        monitor = MainsMonitor()
        monitor.update(None, on_grid())
        monitor.update(None, on_grid())
        monitor.update(None, None)

        announcements = [monitor.update(None, on_battery()) for _ in range(2)]

        self.assertEqual(announcements, [None, GridState.ON_BATTERY])

    def test_update_a_restart_during_an_outage_does_not_announce_the_outage_it_woke_up_inside(self):
        monitor = MainsMonitor()

        announcements = [monitor.update(None, on_battery()) for _ in range(3)]

        self.assertEqual(announcements, [None, None, None])

    def test_update_a_restart_during_an_outage_still_announces_the_grid_coming_back(self):
        monitor = MainsMonitor()
        monitor.update(None, on_battery())
        monitor.update(None, on_battery())

        announcements = [monitor.update(None, on_grid()), monitor.update(None, on_grid())]

        self.assertEqual(announcements, [None, GridState.ON_GRID])

    def test_update_the_hat_announces_an_outage_with_no_station_in_the_flat_at_all(self):
        monitor = MainsMonitor()
        monitor.update(hat(mains_present=True), None)
        monitor.update(hat(mains_present=True), None)

        announcements = [monitor.update(hat(mains_present=False), None) for _ in range(2)]

        self.assertEqual(announcements, [None, GridState.ON_BATTERY])

    def test_update_throwing_the_transfer_switch_mid_outage_does_not_announce_the_light_returning(self):
        """The whole flat moves onto the station, so the hat sees power again — but the city is still out."""
        monitor = MainsMonitor()
        monitor.update(hat(mains_present=True), on_grid())
        monitor.update(hat(mains_present=True), on_grid())
        monitor.update(hat(mains_present=False), on_battery())
        monitor.update(hat(mains_present=False), on_battery())

        announcements = [monitor.update(hat(mains_present=True), on_battery()) for _ in range(3)]

        self.assertEqual(announcements, [None, None, None])

    def test_update_switching_back_to_the_city_announces_the_light_returning(self):
        monitor = MainsMonitor()
        monitor.update(hat(mains_present=True), on_grid())
        monitor.update(hat(mains_present=True), on_grid())
        monitor.update(hat(mains_present=False), on_battery())
        monitor.update(hat(mains_present=False), on_battery())
        monitor.update(hat(mains_present=True), on_battery())

        announcements = [monitor.update(hat(mains_present=True), on_grid()) for _ in range(2)]

        self.assertEqual(announcements, [None, GridState.ON_GRID])


class RenderMainsChangeTestCase(unittest.TestCase):
    def test_render_losing_the_grid_reports_the_charge_and_how_long_it_holds(self):
        text = render_mains_change(GridState.ON_BATTERY, on_battery(battery_percent=82.0, remaining_minutes=95))

        self.assertEqual(text, "🕯 <b>Світло зникло</b>\n\nDelta 2 тримає квартиру — 82%, лишилось ~1 год 35 хв")

    def test_render_losing_the_grid_without_an_estimate_still_reports_the_charge(self):
        text = render_mains_change(GridState.ON_BATTERY, on_battery(battery_percent=82.0, remaining_minutes=None))

        self.assertEqual(text, "🕯 <b>Світло зникло</b>\n\nDelta 2 тримає квартиру — 82%")

    def test_render_the_grid_returning_reports_the_charge_and_that_it_is_filling_again(self):
        text = render_mains_change(GridState.ON_GRID, on_grid(battery_percent=61.0))

        self.assertEqual(text, "💡 <b>Світло є</b>\n\nDelta 2 — 61%, заряджається")

    def test_render_losing_the_grid_without_a_station_still_says_the_light_is_out(self):
        text = render_mains_change(GridState.ON_BATTERY, None)

        self.assertEqual(text, "🕯 <b>Світло зникло</b>")

    def test_render_the_grid_returning_without_a_station_still_says_the_light_is_back(self):
        text = render_mains_change(GridState.ON_GRID, None)

        self.assertEqual(text, "💡 <b>Світло є</b>")
