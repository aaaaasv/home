from datetime import datetime, timedelta, timezone

from src.modules.air_threats.commands import TrackAirThreatsCommand
from src.modules.air_threats.domain import AirThreat, ThreatConfidence, ThreatKind
from src.modules.air_threats.use_cases.track_air_threats import TrackAirThreatsUseCase
from src.tests.integration.base import BaseIntegrationTestCase

# the flat, in the documentation-reserved sense: a point in Kyiv, not the household's own
HOME_LATITUDE = 50.45
HOME_LONGITUDE = 30.52

NEAR_KILOMETRES = 70.0
APPROACH_DEGREES = 30.0
STALE_SECONDS = 180


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

    the two rules answer different fears and must not be collapsed: «щось поруч» needs no course, and
    «летить сюди» is worthless without one.
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
            near_kilometres=NEAR_KILOMETRES,
            approach_degrees=APPROACH_DEGREES,
            inbound_kinds=frozenset({"missile", "ballistic"}),
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

    async def test_track_air_threats_with_a_missile_far_away_pointed_at_us_reports_it_as_inbound(self):
        # south-east of Kyiv, heading north-west — that is straight at the flat
        missile = build_threat(
            tracker_id="trk_missile",
            kind=ThreatKind.MISSILE,
            title="Ракета",
            latitude=49.60,
            longitude=32.00,
            heading_degrees=325.0,
        )

        changes = await self.build_use_case([missile])(self.command())

        self.assertEqual([approaching.threat.tracker_id for approaching in changes.appeared], ["trk_missile"])
        self.assertEqual(changes.appeared[0].is_inbound, True)

    async def test_track_air_threats_with_a_missile_far_away_heading_elsewhere_reports_nothing(self):
        missile = build_threat(
            tracker_id="trk_missile",
            kind=ThreatKind.MISSILE,
            title="Ракета",
            latitude=49.60,
            longitude=32.00,
            heading_degrees=145.0,
        )

        changes = await self.build_use_case([missile])(self.command())

        self.assertEqual(changes.appeared, [])

    async def test_track_air_threats_with_a_missile_far_away_and_no_course_reports_nothing(self):
        missile = build_threat(
            tracker_id="trk_missile",
            kind=ThreatKind.MISSILE,
            title="Ракета",
            latitude=49.60,
            longitude=32.00,
            heading_degrees=None,
        )

        changes = await self.build_use_case([missile])(self.command())

        self.assertEqual(changes.appeared, [])

    async def test_track_air_threats_with_a_drone_far_away_pointed_at_us_still_reports_nothing(self):
        """Only the kinds that cross such a distance are worth a message from it — a drone is not one."""
        drone = build_threat(latitude=49.60, longitude=32.00, heading_degrees=325.0)

        changes = await self.build_use_case([drone])(self.command())

        self.assertEqual(changes.appeared, [])

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
