import unittest

from src.infrastructure.adapters.neptun_air_threat_source import NeptunAirThreatSource, _read_threat
from src.modules.air_threats.domain import ThreatConfidence, ThreatKind

# a record exactly as the map answered on 25.09.2026, kept whole so a changed payload shape fails here first
REAL_RECORD = {
    "id": "trk_00215983",
    "type": "uav",
    "title": "БпЛА",
    "region": "Харківська область",
    "district": "",
    "locality": "Ізюм",
    "lat": 49.079534358725326,
    "lon": 37.58600943160185,
    "heading": 301,
    "confidenceLevel": "medium",
    "sourceCount": 3,
    "updatedAt": "2026-09-25T10:45:30Z",
    "explanationShort": "БпЛА курсом на Ізюм. Підтверджень: 3.",
    "status": "active",
    "confirmedAt": "2026-09-25T10:45:30Z",
    "uncertaintyKm": 4,
    "positionQuality": "approx",
    "lifecycle": "uncertain",
    "displayConfidence": "medium",
    "destination": True,
    "presumptiveCourse": True,
}


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exception):
        return None

    def raise_for_status(self):
        return None

    async def json(self, content_type=None):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exception):
        return None

    def get(self, url, headers=None, timeout=None):
        return FakeResponse(self.payload)


class ReadThreatTestCase(unittest.TestCase):
    """One record of somebody else's undocumented payload, read defensively — a changed field must not crash the bot."""

    def test_read_threat_takes_every_field_the_bot_needs(self):
        threat = _read_threat(REAL_RECORD)

        self.assertEqual(threat.tracker_id, "trk_00215983")
        self.assertEqual(threat.kind, ThreatKind.UAV)
        self.assertEqual(threat.title, "БпЛА")
        self.assertEqual(threat.locality, "Ізюм")
        self.assertEqual(threat.region, "Харківська область")
        self.assertEqual(threat.latitude, 49.079534358725326)
        self.assertEqual(threat.longitude, 37.58600943160185)
        self.assertEqual(threat.heading_degrees, 301.0)
        self.assertEqual(threat.confidence, ThreatConfidence.MEDIUM)
        self.assertEqual(threat.source_count, 3)
        self.assertEqual(threat.uncertainty_kilometres, 4.0)
        self.assertEqual(threat.is_position_confirmed, False)

    def test_read_threat_without_a_heading_keeps_it_empty_rather_than_guessing(self):
        threat = _read_threat(REAL_RECORD | {"heading": None})

        self.assertEqual(threat.heading_degrees, None)

    def test_read_threat_with_a_confirmed_position_says_so(self):
        threat = _read_threat(REAL_RECORD | {"positionQuality": "confirmed"})

        self.assertEqual(threat.is_position_confirmed, True)

    def test_read_threat_of_a_kind_the_bot_has_never_heard_of_is_still_a_threat(self):
        threat = _read_threat(REAL_RECORD | {"type": "something_new"})

        self.assertEqual(threat.kind, ThreatKind.UNKNOWN)

    def test_read_threat_that_is_no_longer_active_is_dropped(self):
        self.assertEqual(_read_threat(REAL_RECORD | {"status": "closed"}), None)

    def test_read_threat_without_a_position_is_dropped(self):
        self.assertEqual(_read_threat(REAL_RECORD | {"lat": None}), None)


class NeptunAirThreatSourceTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_read_active_returns_every_usable_track(self):
        source = NeptunAirThreatSource(
            session_factory=lambda: FakeSession({"serverTime": "…", "threats": [REAL_RECORD, {"id": "broken"}]})
        )

        threats = await source.read_active()

        self.assertEqual([threat.tracker_id for threat in threats], ["trk_00215983"])

    async def test_read_active_with_an_answer_that_is_not_a_threat_list_returns_nothing(self):
        source = NeptunAirThreatSource(session_factory=lambda: FakeSession({"error": "nope"}))

        threats = await source.read_active()

        self.assertEqual(threats, None)
