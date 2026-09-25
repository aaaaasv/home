import unittest
from datetime import datetime, timezone

from src.bot.handlers.air_threats.formatting import render_gone, render_minutes, render_threat
from src.modules.air_threats.domain import AirThreat, ApproachingThreat, ThreatConfidence, ThreatKind

HOME_LATITUDE = 50.45
HOME_LONGITUDE = 30.52


def build_approaching(**overrides) -> ApproachingThreat:
    threat_fields = dict(
        tracker_id="trk_1",
        kind=ThreatKind.UAV,
        title="БпЛА",
        locality="Бровари",
        region="Київська область",
        latitude=50.51,
        longitude=30.79,
        heading_degrees=270.0,
        confidence=ThreatConfidence.MEDIUM,
        source_count=3,
        uncertainty_kilometres=4.0,
        is_position_confirmed=False,
        updated_at=datetime(2026, 9, 25, 10, 45, tzinfo=timezone.utc),
    )
    threat_fields.update(overrides.pop("threat", {}))
    defaults = dict(threat=AirThreat(**threat_fields), distance_kilometres=20.4, is_inbound=False)
    defaults.update(overrides)
    return ApproachingThreat(**defaults)


class RenderThreatTestCase(unittest.TestCase):
    """The card a person reads at three in the morning — it must not imply more certainty than the map has."""

    def test_render_threat_names_what_where_and_how_much_it_is_believed(self):
        text = render_threat(build_approaching(), HOME_LATITUDE, HOME_LONGITUDE)

        self.assertEqual(
            text,
            "🛸 <b>БпЛА</b>\n" "сходу, 20 км (±4 км) · біля Бровари\n" "<i>середнє, підтверджень 3</i>",
        )

    def test_render_threat_that_is_inbound_says_so_in_the_headline(self):
        text = render_threat(
            build_approaching(
                threat={
                    "kind": ThreatKind.MISSILE,
                    "title": "Ракета",
                    "locality": None,
                    "uncertainty_kilometres": None,
                },
                distance_kilometres=180.0,
                is_inbound=True,
                minutes_away=13.5,
            ),
            HOME_LATITUDE,
            HOME_LONGITUDE,
        )

        self.assertEqual(
            text,
            "🚀 <b>Ракета</b> — курсом сюди\n" "сходу, 180 км\n" "підліт ~14 хв\n" "<i>середнє, підтверджень 3</i>",
        )

    def test_render_threat_with_a_confirmed_position_says_so(self):
        text = render_threat(build_approaching(threat={"is_position_confirmed": True}), HOME_LATITUDE, HOME_LONGITUDE)

        self.assertIn("<i>середнє, підтверджень 3, позиція підтверджена</i>", text)

    def test_render_gone_keeps_the_card_and_marks_it(self):
        text = render_gone("🛸 <b>БпЛА</b>\nсходу, 20 км")

        self.assertEqual(text, "🛸 <b>БпЛА</b>\nсходу, 20 км\n\n<b>зникла з мапи</b>")


class RenderMinutesTestCase(unittest.TestCase):
    """Under two minutes a person counts in seconds, and that is exactly when it matters most."""

    def test_render_minutes_under_two_minutes_counts_in_seconds(self):
        self.assertEqual(render_minutes(0.7), "42 с")

    def test_render_minutes_above_two_minutes_counts_in_whole_minutes(self):
        self.assertEqual(render_minutes(13.5), "14 хв")
