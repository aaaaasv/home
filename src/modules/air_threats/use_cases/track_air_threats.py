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

    two rules, and they answer different fears. **Near** is «щось поруч» — anything at all within the radius,
    because a drone that is already overhead does not need a course to matter. **Inbound** is «летить сюди» —
    only the kinds that cross hundreds of kilometres, and only while actually pointed at us; a missile over
    another oblast is not news until its course says otherwise.

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

        relevant = [approaching for approaching in map(lambda t: self._weigh(t, data), threats) if approaching]
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
        if distance <= data.near_kilometres:
            return ApproachingThreat(threat=threat, distance_kilometres=distance, is_inbound=False)

        if threat.kind not in data.inbound_kinds or threat.heading_degrees is None:
            return None

        towards_us = bearing_degrees(threat.latitude, threat.longitude, data.latitude, data.longitude)
        if angle_between_degrees(threat.heading_degrees, towards_us) > data.approach_degrees:
            return None

        return ApproachingThreat(threat=threat, distance_kilometres=distance, is_inbound=True)
