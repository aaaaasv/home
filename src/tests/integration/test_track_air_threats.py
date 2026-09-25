from datetime import datetime, timedelta, timezone

from src.modules.air_threats.commands import TrackAirThreatsCommand
from src.modules.air_threats.domain import AirThreat, ThreatConfidence, ThreatKind
from src.modules.air_threats.use_cases.track_air_threats import TrackAirThreatsUseCase
from src.tests.integration.base import BaseIntegrationTestCase

# the flat, in the documentation-reserved sense: a point in Kyiv, not the household's own
HOME_LATITUDE = 50.45
HOME_LONGITUDE = 30.52

OVERHEAD_KILOMETRES = 25.0
WARNING_MINUTES = 10.0
APPROACH_DEGREES = 30.0
STALE_SECONDS = 180
SPEEDS = {"uav": 180.0, "fpv": 120.0, "missile": 800.0, "ballistic": 2400.0}
DEFAULT_SPEED = 2400.0


class ScriptedThreatSource:
    """Answers with what the test put in it, and with None when the map is meant to be unreachable."""

    def __init__(self, *answers):
        self.answers = list(answers)

    async def read_active(self):
        return self.answers.pop(0) if self.answers else []


def build_threat(**overrides) -> AirThreat:
    defaults = dict(
        tracker_id="trk_1",
        kind=ThreatKind.UAV,
        title="БпЛА",
        locality="Бровари",
        region="Київська область",
        latitude=HOME_LATITUDE,
        longitude=HOME_LONGITUDE,
        heading_degrees=None,
        confidence=ThreatConfidence.MEDIUM,
        source_count=2,
        uncertainty_kilometres=8.0,
        is_position_confirmed=False,
        updated_at=datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return AirThreat(**defaults)


class TrackAirThreatsTestCase(BaseIntegrationTestCase):
    """
    Which of everything in the air earns a message to one household, and what counts as news the second time.

    the two rules answer different fears and must not be collapsed: «щось просто тут» needs no course, and
    «летить сюди» is measured in minutes, because the same distance is twenty minutes of a drone and forty
    seconds of a ballistic missile.
    """

    def build_use_case(self, *answers) -> TrackAirThreatsUseCase:
        return TrackAirThreatsUseCase(
            uow=self.uow,
            source=ScriptedThreatSource(*answers),
            household_calendar=self.household_calendar,
            stale_after_seconds=STALE_SECONDS,
        )

    def command(self, **overrides) -> TrackAirThreatsCommand:
        defaults = dict(
            latitude=HOME_LATITUDE,
            longitude=HOME_LONGITUDE,
            overhead_kilometres=OVERHEAD_KILOMETRES,
            warning_minutes=WARNING_MINUTES,
            approach_degrees=APPROACH_DEGREES,
            speeds_by_kind=SPEEDS,
            default_speed=DEFAULT_SPEED,
        )
        defaults.update(overrides)
        return TrackAirThreatsCommand(**defaults)

    async def test_track_air_threats_with_a_drone_overhead_reports_it_without_needing_a_course(self):
        overhead = build_threat(latitude=50.50, longitude=30.60, heading_degrees=None)

        changes = await self.build_use_case([overhead])(self.command())

        self.assertEqual([approaching.threat.tracker_id for approaching in changes.appeared], ["trk_1"])
        self.assertEqual(changes.appeared[0].is_inbound, False)
        self.assertEqual(round(changes.appeared[0].distance_kilometres), 8)

    async def test_track_air_threats_with_a_drone_far_away_reports_nothing(self):
        far_drone = build_threat(latitude=49.99, longitude=36.23, heading_degrees=300.0)

        changes = await self.build_use_case([far_drone])(self.command())

        self.assertEqual(changes.appeared, [])
        self.assertEqual(changes.standing, [])

    async def test_track_air_threats_with_a_ballistic_far_away_pointed_at_us_reports_it_as_inbound(self):
        """150 km is under four minutes at ballistic speed — inside the window and worth the ping."""
        # south-east of Kyiv, heading north-west — that is straight at the flat
        ballistic = build_threat(
            tracker_id="trk_ballistic",
            kind=ThreatKind.BALLISTIC,
            title="Балістика",
            latitude=49.60,
            longitude=32.00,
            heading_degrees=325.0,
        )

        changes = await self.build_use_case([ballistic])(self.command())

        self.assertEqual([approaching.threat.tracker_id for approaching in changes.appeared], ["trk_ballistic"])
        self.assertEqual(changes.appeared[0].is_inbound, True)
        self.assertEqual(round(changes.appeared[0].minutes_away, 1), 3.5)

    async def test_track_air_threats_with_a_cruise_missile_still_too_far_in_time_reports_nothing(self):
        """The same 150 km is eleven minutes at cruise speed — outside the window, so it waits."""
        missile = build_threat(
            tracker_id="trk_missile",
            kind=ThreatKind.MISSILE,
            title="Ракета",
            latitude=49.60,
            longitude=32.00,
            heading_degrees=325.0,
        )

        changes = await self.build_use_case([missile])(self.command())

        self.assertEqual(changes.appeared, [])

    async def test_track_air_threats_with_a_drone_pointed_at_us_inside_the_window_reports_it_too(self):
        """A slow thing qualifies at a short distance — the rule is time, so no kind is excluded by name."""
        drone = build_threat(latitude=50.68, longitude=30.60, heading_degrees=190.0)

        changes = await self.build_use_case([drone])(self.command())

        self.assertEqual([approaching.threat.tracker_id for approaching in changes.appeared], ["trk_1"])
        self.assertEqual(changes.appeared[0].is_inbound, True)

    async def test_track_air_threats_with_a_missile_far_away_heading_elsewhere_reports_nothing(self):
        missile = build_threat(
            tracker_id="trk_missile",
            kind=ThreatKind.BALLISTIC,
            title="Балістика",
            latitude=49.60,
            longitude=32.00,
            heading_degrees=145.0,
        )

        changes = await self.build_use_case([missile])(self.command())

        self.assertEqual(changes.appeared, [])

    async def test_track_air_threats_with_a_missile_far_away_and_no_course_reports_nothing(self):
        missile = build_threat(
            tracker_id="trk_missile",
            kind=ThreatKind.BALLISTIC,
            title="Балістика",
            latitude=49.60,
            longitude=32.00,
            heading_degrees=None,
        )

        changes = await self.build_use_case([missile])(self.command())

        self.assertEqual(changes.appeared, [])

    async def test_track_air_threats_of_an_unknown_kind_is_timed_as_the_fastest_thing_we_know(self):
        """Warning too early costs a glance; too late costs the point — so an unfamiliar track is treated as fast."""
        unknown = build_threat(
            tracker_id="trk_unknown", kind=ThreatKind.UNKNOWN, latitude=49.60, longitude=32.00, heading_degrees=325.0
        )

        changes = await self.build_use_case([unknown])(self.command())

        self.assertEqual([approaching.threat.tracker_id for approaching in changes.appeared], ["trk_unknown"])

    async def test_track_air_threats_seeing_the_same_track_twice_reports_it_as_standing_not_new(self):
        overhead = build_threat(latitude=50.50, longitude=30.60)
        use_case = self.build_use_case([overhead])
        await use_case(self.command())

        changes = await self.build_use_case([overhead])(self.command())

        self.assertEqual(changes.appeared, [])
        self.assertEqual([approaching.threat.tracker_id for approaching in changes.standing], ["trk_1"])

    async def test_track_air_threats_when_a_track_vanishes_reports_it_gone_only_after_the_stale_window(self):
        overhead = build_threat(latitude=50.50, longitude=30.60)
        await self.build_use_case([overhead])(self.command())

        just_vanished = await self.build_use_case([])(self.command())

        self.assertEqual(just_vanished.gone, [])

    async def test_track_air_threats_reports_a_track_gone_once_it_has_been_missing_long_enough(self):
        overhead = build_threat(latitude=50.50, longitude=30.60)
        await self.build_use_case([overhead])(self.command())
        self.household_calendar.frozen_now += timedelta(seconds=STALE_SECONDS + 1)

        changes = await self.build_use_case([])(self.command())

        self.assertEqual(changes.gone, ["trk_1"])

    async def test_track_air_threats_with_an_unreachable_map_reports_nothing_and_closes_nothing(self):
        overhead = build_threat(latitude=50.50, longitude=30.60)
        await self.build_use_case([overhead])(self.command())
        self.household_calendar.frozen_now += timedelta(seconds=STALE_SECONDS + 1)

        changes = await self.build_use_case(None)(self.command())

        self.assertEqual(changes, None)
        async with self.uow as uow:
            still_open = await uow.air_threat_notices.list_open()
        self.assertEqual([notice.tracker_id for notice in still_open], ["trk_1"])

    async def test_track_air_threats_reopening_a_closed_track_announces_it_again(self):
        overhead = build_threat(latitude=50.50, longitude=30.60)
        await self.build_use_case([overhead])(self.command())
        self.household_calendar.frozen_now += timedelta(seconds=STALE_SECONDS + 1)
        await self.build_use_case([])(self.command())

        changes = await self.build_use_case([overhead])(self.command())

        self.assertEqual([approaching.threat.tracker_id for approaching in changes.appeared], ["trk_1"])
