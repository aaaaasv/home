from datetime import timedelta

from src.common.household_calendar import HouseholdCalendar
from src.common.use_case import BaseUseCase
from src.infrastructure.db.uow import UnitOfWork
from src.modules.air_threats.commands import TrackAirThreatsCommand
from src.modules.air_threats.domain import AirThreat, AirThreatChanges, ApproachingThreat
from src.modules.air_threats.services.air_threat_source import AirThreatSource
from src.modules.air_threats.services.geography import angle_between_degrees, bearing_degrees, distance_kilometres


class TrackAirThreatsUseCase(BaseUseCase):
    """
    Decides which of everything in the air is worth telling one household about, and what changed since last time.

    two rules, and they answer different fears. **Overhead** is «щось просто тут» — close enough that it matters
    whatever it is and whichever way it points, because a drone above the roof needs no course to be a fact.
    **Inbound** is «летить сюди», and it is measured in **minutes, not kilometres**: the same seventy kilometres
    is twenty-three minutes of a piston Shahed and forty-one seconds of something at Mach 5, and what the person
    does with a warning — put shoes on and go down — costs minutes either way.

    a track missing its heading can never be inbound. that is deliberate: guessing a course from a single
    position is exactly the invention that would make this feature lie.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        source: AirThreatSource,
        household_calendar: HouseholdCalendar,
        stale_after_seconds: int,
    ):
        super().__init__(uow)
        self.source = source
        self.household_calendar = household_calendar
        self.stale_after_seconds = stale_after_seconds

    async def __call__(self, data: TrackAirThreatsCommand) -> AirThreatChanges | None:
        threats = await self.source.read_active()
        if threats is None:
            # the map is unreachable; saying nothing is right, and closing every open card would be a lie
            return None

        relevant = [approaching for approaching in (self._weigh(threat, data) for threat in threats) if approaching]
        moment = self.household_calendar.now()

        async with self.uow as uow:
            open_notices = {notice.tracker_id: notice for notice in await uow.air_threat_notices.list_open()}

            appeared: list[ApproachingThreat] = []
            standing: list[ApproachingThreat] = []
            for approaching in relevant:
                tracker_id = approaching.threat.tracker_id
                if tracker_id in open_notices:
                    await uow.air_threat_notices.mark_seen(tracker_id, moment)
                    standing.append(approaching)
                else:
                    await uow.air_threat_notices.open_notice(tracker_id, moment)
                    appeared.append(approaching)

            still_here = {approaching.threat.tracker_id for approaching in relevant}
            gone = [
                notice.tracker_id
                for notice in open_notices.values()
                if notice.tracker_id not in still_here
                and moment - notice.last_seen_at > timedelta(seconds=self.stale_after_seconds)
            ]
            for tracker_id in gone:
                await uow.air_threat_notices.close_notice(tracker_id, moment)

        return AirThreatChanges(appeared=appeared, standing=standing, gone=gone)

    def _weigh(self, threat: AirThreat, data: TrackAirThreatsCommand) -> ApproachingThreat | None:
        distance = distance_kilometres(data.latitude, data.longitude, threat.latitude, threat.longitude)
        if distance <= data.overhead_kilometres:
            return ApproachingThreat(
                threat=threat,
                distance_kilometres=distance,
                is_inbound=False,
                minutes_away=self._minutes_away(distance, threat, data),
            )

        if threat.heading_degrees is None:
            return None

        towards_us = bearing_degrees(threat.latitude, threat.longitude, data.latitude, data.longitude)
        if angle_between_degrees(threat.heading_degrees, towards_us) > data.approach_degrees:
            return None

        minutes = self._minutes_away(distance, threat, data)
        if minutes > data.warning_minutes:
            return None

        return ApproachingThreat(threat=threat, distance_kilometres=distance, is_inbound=True, minutes_away=minutes)

    def _minutes_away(self, distance: float, threat: AirThreat, data: TrackAirThreatsCommand) -> float:
        """
        How long it would take at this kind's usual speed — the map gives a course but never a speed.

        an unfamiliar kind is treated as the fastest one we know rather than the slowest: warning too early
        costs a glance at the phone, warning too late costs the whole point of the feature.
        """
        speed = data.speeds_by_kind.get(threat.kind, data.default_speed)
        return distance / speed * 60
