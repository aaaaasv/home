from unittest import TestCase

from src.modules.shopping.domain import ReputabilityPolicy, ShopOffer, build_tracked_product

POLICY = ReputabilityPolicy(minimum_rating=80, minimum_reviews=100, trusted_firm_ids=frozenset({42}))


def offer(price: int, firm_id: int = 1, rating: int = 95, reviews: int = 500, is_new: bool = True, offer_id=None):
    return ShopOffer(
        firm_id=firm_id,
        shop=f"Shop {firm_id}",
        price=price,
        rating=rating,
        reviews=reviews,
        is_new=is_new,
        offer_id=offer_id,
    )


class BuildTrackedProductTestCase(TestCase):
    def test_build_tracked_product_picks_the_cheapest_reputable_offer_over_a_cheaper_shady_one(self):
        offers = [offer(59500, firm_id=1, rating=30, reviews=2), offer(60500, firm_id=2, rating=95, reviews=500)]

        product = build_tracked_product("X-T50", offers, naive_minimum=59500, policy=POLICY)

        self.assertEqual(product.price, 60500)
        self.assertEqual(product.shop, "Shop 2")
        self.assertTrue(product.is_reputable)
        self.assertEqual(product.naive_minimum, 59500)

    def test_build_tracked_product_trusts_an_allowlisted_shop_below_the_rating_bar(self):
        offers = [offer(61000, firm_id=42, rating=10, reviews=0, offer_id=777)]

        product = build_tracked_product("X-T50", offers, naive_minimum=61000, policy=POLICY)

        self.assertEqual(product.price, 61000)
        self.assertTrue(product.is_reputable)
        self.assertEqual(product.buy_link, "https://hotline.ua/go/price/777/")

    def test_build_tracked_product_rejects_a_shop_below_the_reviews_bar(self):
        offers = [offer(60000, firm_id=3, rating=99, reviews=99), offer(62000, firm_id=4, rating=99, reviews=100)]

        product = build_tracked_product("X-T50", offers, naive_minimum=60000, policy=POLICY)

        self.assertEqual(product.price, 62000)
        self.assertTrue(product.is_reputable)

    def test_build_tracked_product_never_counts_a_used_offer_as_reputable(self):
        offers = [offer(50000, firm_id=42, is_new=False), offer(63000, firm_id=5, rating=95, reviews=500)]

        product = build_tracked_product("X-T50", offers, naive_minimum=50000, policy=POLICY)

        self.assertEqual(product.price, 63000)
        self.assertTrue(product.is_reputable)

    def test_build_tracked_product_falls_back_to_the_cheapest_new_offer_when_none_are_reputable(self):
        offers = [offer(59500, firm_id=6, rating=20, reviews=1), offer(61000, firm_id=7, rating=40, reviews=3)]

        product = build_tracked_product("X-T50", offers, naive_minimum=59500, policy=POLICY)

        self.assertEqual(product.price, 59500)
        self.assertFalse(product.is_reputable)
        self.assertEqual(product.shop, "Shop 6")

    def test_build_tracked_product_ignores_a_cheaper_used_offer_in_the_fallback(self):
        offers = [
            offer(48000, firm_id=8, rating=20, reviews=1, is_new=False),
            offer(59500, firm_id=9, rating=20, reviews=1),
        ]

        product = build_tracked_product("X-T50", offers, naive_minimum=48000, policy=POLICY)

        self.assertEqual(product.price, 59500)
        self.assertFalse(product.is_reputable)

    def test_build_tracked_product_with_only_used_offers_falls_back_to_the_naive_minimum(self):
        offers = [offer(48000, firm_id=8, is_new=False), offer(49000, firm_id=9, is_new=False)]

        product = build_tracked_product("X-T50", offers, naive_minimum=48000, policy=POLICY)

        self.assertEqual(product.price, 48000)
        self.assertFalse(product.is_reputable)
        self.assertIsNone(product.shop)
