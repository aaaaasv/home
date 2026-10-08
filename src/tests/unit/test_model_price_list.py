import unittest

from src.modules.model_budget.services.price_list import MODEL_PRICES, price_of


class PriceOfTestCase(unittest.TestCase):
    """What a call cost, in millionths of a dollar — the guard counts money, not tokens."""

    def test_price_of_a_known_model_follows_its_published_rates(self):
        # opus 5.5 is $4 in and $20 out per million: 1 000 000 × $4 = $4, 1 000 000 × $20 = $20
        self.assertEqual(price_of("claude-opus-5-5", 1_000_000, 1_000_000), 24_000_000)

    def test_price_of_a_real_photo_review_is_a_fraction_of_a_cent(self):
        """The shape measured on this house's own photos: ~1 300 tokens in, ~80 out."""
        self.assertEqual(price_of("claude-opus-5-5", 1300, 80), 6800)

    def test_price_of_the_cheapest_model_is_counted_too_rather_than_rounded_away(self):
        self.assertEqual(price_of("claude-haiku-4-5-20251001", 1_000_000, 1_000_000), 600_000)

    def test_price_of_a_model_nobody_listed_is_charged_at_the_dearest_rate(self):
        """A typo in a setting must not read as free, or the guard quietly stops guarding."""
        dearest = max(price_of(model, 1000, 1000) for model in MODEL_PRICES)

        self.assertEqual(price_of("claude-whatever-9", 1000, 1000), dearest)

    def test_price_of_a_call_that_produced_nothing_is_the_input_alone(self):
        self.assertEqual(price_of("claude-sonnet-5-5", 1_000_000, 0), 2_000_000)
