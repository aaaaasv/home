import unittest
from datetime import datetime, timedelta, timezone

from src.bot.handlers.power.formatting import render_reserve_board
from src.modules.power.domain import EcoFlowState, GridState, MediaServerState, ReserveLayer, ReserveStanding, UpsState
from src.modules.power.reserve import ElapsedClock, build_reserve

NOW = datetime(2026, 9, 9, 12, 40, tzinfo=timezone.utc)


def station(**overrides) -> EcoFlowState:
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
        as_of=NOW,
    )
    defaults.update(overrides)
    return EcoFlowState(**defaults)


def charging_station(**overrides) -> EcoFlowState:
    return station(**{"ac_input_power": 310, "ac_output_power": 0, "remaining_minutes": 60, **overrides})


def discharging_station(**overrides) -> EcoFlowState:
    defaults = {"ac_input_power": 0, "ac_output_power": 90, "on_mains": False, "remaining_minutes": 130}
    return station(**{**defaults, **overrides})


def idle_station(**overrides) -> EcoFlowState:
    """Sitting on mains at its charge limit with nothing plugged in — draws nothing, feeds nothing."""
    return station(ac_input_power=0, ac_output_power=0, on_mains=False, remaining_minutes=None, **overrides)


def hat(mains_present: bool, battery_volts: float = 4.199, battery_percent: float = 99.1) -> UpsState:
    return UpsState(
        mains_present=mains_present, battery_volts=battery_volts, battery_percent=battery_percent, as_of=NOW
    )


def laptop(**overrides) -> MediaServerState:
    defaults = dict(
        on_mains=True,
        is_charging=False,
        charge_percent=64.0,
        energy_watt_hours=20.194,
        power_watts=0.0,
        as_of=NOW,
    )
    defaults.update(overrides)
    return MediaServerState(**defaults)


def discharging_laptop(**overrides) -> MediaServerState:
    defaults = {"on_mains": False, "is_charging": False, "energy_watt_hours": 20.194, "power_watts": 10.0}
    return laptop(**{**defaults, **overrides})


def row_of(reserve, layer: ReserveLayer):
    return next(row for row in reserve.rows if row.layer is layer)


class BuildReserveStationRowTestCase(unittest.TestCase):
    """
    The one layer that measures its own runtime, so its row is read off the station's own watts and nothing else.

    `on_mains` is not consulted anywhere here: it reports false on a full station idling on mains, which is
    exactly the reading that would otherwise be drawn as a blackout.
    """

    def test_build_reserve_with_a_station_drawing_from_the_wall_shows_it_charging(self):
        reserve = build_reserve(
            grid=GridState.ON_GRID,
            station=charging_station(),
            ups=hat(mains_present=True),
            router_alive=True,
            media_server=laptop(),
            on_battery_for=None,
            socket_dead_for=None,
        )

        row = row_of(reserve, ReserveLayer.STATION)

        self.assertEqual((row.standing, row.remaining), (ReserveStanding.CHARGING, timedelta(minutes=60)))

    def test_build_reserve_with_a_station_feeding_the_flat_shows_how_long_it_holds(self):
        reserve = build_reserve(
            grid=GridState.ON_BATTERY,
            station=discharging_station(),
            ups=hat(mains_present=False),
            router_alive=True,
            media_server=laptop(),
            on_battery_for=timedelta(minutes=40),
            socket_dead_for=timedelta(minutes=40),
        )

        row = row_of(reserve, ReserveLayer.STATION)

        self.assertEqual((row.standing, row.remaining), (ReserveStanding.HOLDING, timedelta(minutes=130)))

    def test_build_reserve_with_an_idle_full_station_shows_it_full_rather_than_holding(self):
        reserve = build_reserve(
            grid=GridState.ON_GRID,
            station=idle_station(),
            ups=hat(mains_present=True),
            router_alive=True,
            media_server=laptop(),
            on_battery_for=None,
            socket_dead_for=None,
        )

        row = row_of(reserve, ReserveLayer.STATION)

        self.assertEqual((row.standing, row.remaining), (ReserveStanding.FULL, None))

    def test_build_reserve_with_an_unreachable_station_says_so_rather_than_leaving_the_row_out(self):
        reserve = build_reserve(
            grid=GridState.ON_GRID,
            station=None,
            ups=hat(mains_present=True),
            router_alive=True,
            media_server=laptop(),
            on_battery_for=None,
            socket_dead_for=None,
        )

        row = row_of(reserve, ReserveLayer.STATION)

        self.assertEqual((row.standing, row.remaining), (ReserveStanding.UNREACHABLE, None))


class BuildReservePiRowTestCase(unittest.TestCase):
    """
    The hat knows whether its socket is live and how full its pack is, and nothing at all about how long it lasts.

    the fullness question is settled on volts, never on the gauge's percent: the gauge re-learns the pack after
    a cell swap and reads nonsense meanwhile — 4% at 3.78 V on 08.09, which was really about 45%.
    """

    def test_build_reserve_with_a_rested_pack_on_a_live_socket_shows_the_pi_full(self):
        reserve = build_reserve(
            grid=GridState.ON_GRID,
            station=charging_station(),
            ups=hat(mains_present=True, battery_volts=4.199),
            router_alive=True,
            media_server=laptop(),
            on_battery_for=None,
            socket_dead_for=None,
        )

        row = row_of(reserve, ReserveLayer.PI)

        self.assertEqual((row.standing, row.remaining, row.holding_for), (ReserveStanding.FULL, None, None))

    def test_build_reserve_with_a_pack_below_the_full_mark_shows_the_pi_charging(self):
        reserve = build_reserve(
            grid=GridState.ON_GRID,
            station=charging_station(),
            ups=hat(mains_present=True, battery_volts=3.95),
            router_alive=True,
            media_server=laptop(),
            on_battery_for=None,
            socket_dead_for=None,
        )

        row = row_of(reserve, ReserveLayer.PI)

        self.assertEqual(row.standing, ReserveStanding.CHARGING)

    def test_build_reserve_with_a_dead_socket_shows_how_long_the_pi_has_been_on_its_pack(self):
        reserve = build_reserve(
            grid=GridState.ON_BATTERY,
            station=discharging_station(),
            ups=hat(mains_present=False),
            router_alive=True,
            media_server=laptop(),
            on_battery_for=timedelta(minutes=40),
            socket_dead_for=timedelta(minutes=40),
        )

        row = row_of(reserve, ReserveLayer.PI)

        self.assertEqual((row.standing, row.holding_for), (ReserveStanding.HOLDING_UNMEASURED, timedelta(minutes=40)))

    def test_build_reserve_with_a_silent_agent_shows_the_pi_unreachable(self):
        reserve = build_reserve(
            grid=GridState.ON_GRID,
            station=charging_station(),
            ups=None,
            router_alive=True,
            media_server=laptop(),
            on_battery_for=None,
            socket_dead_for=None,
        )

        row = row_of(reserve, ReserveLayer.PI)

        self.assertEqual(row.standing, ReserveStanding.UNREACHABLE)


class BuildReserveRouterRowTestCase(unittest.TestCase):
    """
    The 2E has no data interface at all, so this row is a reachability probe plus what the hat says about the socket.

    the one thing it must never do is invent the number it is least able to give: with no hat to ask, the row
    stops at "alive" rather than claiming the router is running on its battery.
    """

    def test_build_reserve_with_a_live_socket_shows_the_router_simply_alive(self):
        reserve = build_reserve(
            grid=GridState.ON_GRID,
            station=charging_station(),
            ups=hat(mains_present=True),
            router_alive=True,
            media_server=laptop(),
            on_battery_for=None,
            socket_dead_for=None,
        )

        row = row_of(reserve, ReserveLayer.ROUTER)

        self.assertEqual((row.standing, row.holding_for), (ReserveStanding.ALIVE, None))

    def test_build_reserve_with_a_dead_socket_shows_how_long_the_router_has_been_on_its_own_battery(self):
        reserve = build_reserve(
            grid=GridState.ON_BATTERY,
            station=discharging_station(),
            ups=hat(mains_present=False),
            router_alive=True,
            media_server=laptop(),
            on_battery_for=timedelta(minutes=40),
            socket_dead_for=timedelta(minutes=40),
        )

        row = row_of(reserve, ReserveLayer.ROUTER)

        self.assertEqual((row.standing, row.holding_for), (ReserveStanding.HOLDING_UNMEASURED, timedelta(minutes=40)))

    def test_build_reserve_without_a_hat_never_claims_the_router_is_on_battery(self):
        reserve = build_reserve(
            grid=GridState.ON_BATTERY,
            station=discharging_station(),
            ups=None,
            router_alive=True,
            media_server=laptop(),
            on_battery_for=timedelta(minutes=40),
            socket_dead_for=None,
        )

        row = row_of(reserve, ReserveLayer.ROUTER)

        self.assertEqual(row.standing, ReserveStanding.ALIVE)

    def test_build_reserve_with_a_router_that_does_not_answer_shows_it_unreachable(self):
        reserve = build_reserve(
            grid=GridState.ON_BATTERY,
            station=discharging_station(),
            ups=hat(mains_present=False),
            router_alive=False,
            media_server=laptop(),
            on_battery_for=timedelta(minutes=40),
            socket_dead_for=timedelta(minutes=40),
        )

        row = row_of(reserve, ReserveLayer.ROUTER)

        self.assertEqual(row.standing, ReserveStanding.UNREACHABLE)


class BuildReserveTwoClocksTestCase(unittest.TestCase):
    """
    The city and the wall socket are not the same thing, and the transfer switch is where they part company.

    thrown mid-outage it puts the whole flat on the station: the socket comes back to life, so the pi and the
    router stop holding and start charging, while the city is still out and the heading has to keep saying so.
    """

    def test_build_reserve_after_the_transfer_switch_shows_the_rows_charging_under_an_on_battery_heading(self):
        reserve = build_reserve(
            grid=GridState.ON_BATTERY,
            station=discharging_station(),
            ups=hat(mains_present=True, battery_volts=3.95),
            router_alive=True,
            media_server=laptop(),
            on_battery_for=timedelta(minutes=40),
            socket_dead_for=None,
        )

        standings = {row.layer: row.standing for row in reserve.rows}

        self.assertEqual(
            (reserve.grid, reserve.on_battery_for, standings[ReserveLayer.PI], standings[ReserveLayer.ROUTER]),
            (GridState.ON_BATTERY, timedelta(minutes=40), ReserveStanding.CHARGING, ReserveStanding.ALIVE),
        )

    def test_build_reserve_on_the_grid_drops_the_heading_duration_even_when_a_clock_is_still_running(self):
        reserve = build_reserve(
            grid=GridState.ON_GRID,
            station=charging_station(),
            ups=hat(mains_present=True),
            router_alive=True,
            media_server=laptop(),
            on_battery_for=timedelta(minutes=40),
            socket_dead_for=None,
        )

        self.assertIsNone(reserve.on_battery_for)


class ElapsedClockTestCase(unittest.TestCase):
    """
    How long something has been true, counted only from a start somebody actually watched.

    the same refusal `MainsMonitor` makes when it declines to announce the outage it woke up inside: a bot that
    comes up mid-blackout must not report it as one minute old.
    """

    def test_update_counts_from_the_reading_that_watched_the_state_begin(self):
        clock = ElapsedClock()
        clock.update(False, NOW)

        clock.update(True, NOW + timedelta(minutes=1))
        elapsed = clock.update(True, NOW + timedelta(minutes=41))

        self.assertEqual(elapsed, timedelta(minutes=40))

    def test_update_says_nothing_about_a_state_that_was_already_true_when_it_started_watching(self):
        clock = ElapsedClock()

        elapsed = [clock.update(True, NOW + timedelta(minutes=minute)) for minute in range(3)]

        self.assertEqual(elapsed, [None, None, None])

    def test_update_after_the_state_clears_starts_the_next_stretch_from_scratch(self):
        clock = ElapsedClock()
        clock.update(False, NOW)
        clock.update(True, NOW + timedelta(minutes=1))
        clock.update(False, NOW + timedelta(minutes=10))

        clock.update(True, NOW + timedelta(minutes=20))
        elapsed = clock.update(True, NOW + timedelta(minutes=25))

        self.assertEqual(elapsed, timedelta(minutes=5))


class BuildReserveMediaServerRowTestCase(unittest.TestCase):
    """
    The only layer that can give both numbers honestly — the kernel counts watt-hours and watts for its own pack.

    the runtime comes from energy over power and never from the percent, because a standing 60% charge cap
    keeps `energy_full` from ever recalibrating: on 09.09.2026 the kernel read 64% against a 60% ceiling.
    """

    def test_build_reserve_with_a_laptop_sitting_at_its_charge_cap_shows_it_full(self):
        reserve = build_reserve(
            grid=GridState.ON_GRID,
            station=charging_station(),
            ups=hat(mains_present=True),
            router_alive=True,
            media_server=laptop(on_mains=True, is_charging=False),
            on_battery_for=None,
            socket_dead_for=None,
        )

        row = row_of(reserve, ReserveLayer.MEDIA_SERVER)

        self.assertEqual((row.standing, row.charge_percent), (ReserveStanding.FULL, 64))

    def test_build_reserve_with_a_laptop_filling_shows_it_charging(self):
        reserve = build_reserve(
            grid=GridState.ON_GRID,
            station=charging_station(),
            ups=hat(mains_present=True),
            router_alive=True,
            media_server=laptop(on_mains=True, is_charging=True),
            on_battery_for=None,
            socket_dead_for=None,
        )

        row = row_of(reserve, ReserveLayer.MEDIA_SERVER)

        self.assertEqual(row.standing, ReserveStanding.CHARGING)

    def test_build_reserve_with_a_discharging_laptop_divides_its_watt_hours_by_its_watts(self):
        reserve = build_reserve(
            grid=GridState.ON_BATTERY,
            station=discharging_station(),
            ups=hat(mains_present=False),
            router_alive=True,
            media_server=discharging_laptop(energy_watt_hours=20.0, power_watts=10.0),
            on_battery_for=timedelta(minutes=40),
            socket_dead_for=timedelta(minutes=40),
        )

        row = row_of(reserve, ReserveLayer.MEDIA_SERVER)

        self.assertEqual((row.standing, row.remaining), (ReserveStanding.HOLDING, timedelta(hours=2)))

    def test_build_reserve_with_a_laptop_drawing_nothing_off_mains_reports_no_runtime_rather_than_forever(self):
        reserve = build_reserve(
            grid=GridState.ON_BATTERY,
            station=discharging_station(),
            ups=hat(mains_present=False),
            router_alive=True,
            media_server=discharging_laptop(power_watts=0.0),
            on_battery_for=timedelta(minutes=40),
            socket_dead_for=timedelta(minutes=40),
        )

        row = row_of(reserve, ReserveLayer.MEDIA_SERVER)

        self.assertEqual(
            (row.standing, row.remaining, row.holding_for),
            (ReserveStanding.HOLDING_UNMEASURED, None, timedelta(minutes=40)),
        )

    def test_build_reserve_with_a_laptop_that_is_off_shows_it_unreachable(self):
        reserve = build_reserve(
            grid=GridState.ON_BATTERY,
            station=discharging_station(),
            ups=hat(mains_present=False),
            router_alive=True,
            media_server=None,
            on_battery_for=timedelta(minutes=40),
            socket_dead_for=timedelta(minutes=40),
        )

        row = row_of(reserve, ReserveLayer.MEDIA_SERVER)

        self.assertEqual((row.standing, row.charge_percent), (ReserveStanding.UNREACHABLE, None))


class ReserveChargePercentTestCase(unittest.TestCase):
    """A percent is shown wherever one is measured, and a percent nobody measures is never invented."""

    def test_build_reserve_with_a_gauge_reading_over_full_shows_a_hundred_rather_than_a_broken_number(self):
        reserve = build_reserve(
            grid=GridState.ON_GRID,
            station=charging_station(),
            ups=hat(mains_present=True, battery_percent=101.8),
            router_alive=True,
            media_server=laptop(),
            on_battery_for=None,
            socket_dead_for=None,
        )

        row = row_of(reserve, ReserveLayer.PI)

        self.assertEqual(row.charge_percent, 100)

    def test_build_reserve_never_puts_a_charge_on_the_router(self):
        reserve = build_reserve(
            grid=GridState.ON_GRID,
            station=charging_station(),
            ups=hat(mains_present=True),
            router_alive=True,
            media_server=laptop(),
            on_battery_for=None,
            socket_dead_for=None,
        )

        row = row_of(reserve, ReserveLayer.ROUTER)

        self.assertIsNone(row.charge_percent)


class RenderReserveBoardTestCase(unittest.TestCase):
    """One heading for the grid, then every layer in the same shape: what it holds, then how long that lasts."""

    def test_render_on_battery_reports_the_charge_and_the_time_left_for_every_layer_that_has_them(self):
        reserve = build_reserve(
            grid=GridState.ON_BATTERY,
            station=discharging_station(),
            ups=hat(mains_present=False),
            router_alive=True,
            media_server=discharging_laptop(energy_watt_hours=20.0, power_watts=10.0),
            on_battery_for=timedelta(minutes=40),
            socket_dead_for=timedelta(minutes=40),
        )

        text = render_reserve_board(reserve, NOW)

        self.assertEqual(
            text,
            "🕯 <b>Резерв</b> — на батареї 40 хв\n"
            "\n"
            "⚡ Delta 2 — 82% · лишилось ~2 год 10 хв\n"
            "🖥 Pi — 99% · на батареї 40 хв\n"
            "📡 Роутер — на батареї 40 хв\n"
            "💻 Медіасервер — 64% · лишилось ~2 год\n"
            "\n"
            "<i>станом на 12:40</i>",
        )

    def test_render_on_the_grid_reports_what_is_filling_and_what_is_done(self):
        reserve = build_reserve(
            grid=GridState.ON_GRID,
            station=charging_station(),
            ups=hat(mains_present=True),
            router_alive=True,
            media_server=laptop(),
            on_battery_for=None,
            socket_dead_for=None,
        )

        text = render_reserve_board(reserve, NOW)

        self.assertEqual(
            text,
            "🔌 <b>Резерв</b> — від мережі\n"
            "\n"
            "⚡ Delta 2 — 82% · заряджається · до повного ~1 год\n"
            "🖥 Pi — 99% · повний\n"
            "📡 Роутер — живий\n"
            "💻 Медіасервер — 64% · повний\n"
            "\n"
            "<i>станом на 12:40</i>",
        )

    def test_render_with_nothing_able_to_say_leaves_the_heading_open_rather_than_guessing(self):
        reserve = build_reserve(
            grid=GridState.UNKNOWN,
            station=None,
            ups=None,
            router_alive=False,
            media_server=None,
            on_battery_for=None,
            socket_dead_for=None,
        )

        text = render_reserve_board(reserve, NOW)

        self.assertEqual(
            text,
            "❔ <b>Резерв</b>\n"
            "\n"
            "⚡ Delta 2 — не відповідає\n"
            "🖥 Pi — не відповідає\n"
            "📡 Роутер — не відповідає\n"
            "💻 Медіасервер — не відповідає\n"
            "\n"
            "<i>станом на 12:40</i>",
        )

    def test_render_an_outage_the_bot_woke_up_inside_says_it_is_on_battery_without_inventing_a_duration(self):
        reserve = build_reserve(
            grid=GridState.ON_BATTERY,
            station=discharging_station(remaining_minutes=None),
            ups=hat(mains_present=False),
            router_alive=True,
            media_server=discharging_laptop(power_watts=0.0),
            on_battery_for=None,
            socket_dead_for=None,
        )

        text = render_reserve_board(reserve, NOW)

        self.assertEqual(
            text,
            "🕯 <b>Резерв</b> — на батареї\n"
            "\n"
            "⚡ Delta 2 — 82% · на батареї\n"
            "🖥 Pi — 99% · на батареї\n"
            "📡 Роутер — на батареї\n"
            "💻 Медіасервер — 64% · на батареї\n"
            "\n"
            "<i>станом на 12:40</i>",
        )
