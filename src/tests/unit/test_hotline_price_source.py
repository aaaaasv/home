from unittest import TestCase

from src.infrastructure.adapters.hotline_price_source import HotlinePriceSource
from src.modules.shopping.domain import ReputabilityPolicy

SOURCE = HotlinePriceSource(
    policy=ReputabilityPolicy(minimum_rating=80, minimum_reviews=100),
    donor_category_url="https://hotline.ua/ua/computer/noutbuki/",
)


class ExtractSlugTestCase(TestCase):
    def test_extract_slug_takes_the_last_path_segment(self):
        slug = SOURCE._extract_slug(
            "https://hotline.ua/ua/photo-fotoapparaty-cifrovye/fujifilm-x-t50-body-silver-16828284/"
        )

        self.assertEqual(slug, "fujifilm-x-t50-body-silver-16828284")

    def test_extract_slug_drops_a_query_string(self):
        slug = SOURCE._extract_slug("https://hotline.ua/ua/av-televizory/tcl-75c6k/?tab=prices&filter=sales")

        self.assertEqual(slug, "tcl-75c6k")


class BuildNameTestCase(TestCase):
    def test_build_name_prefixes_the_vendor_and_strips_the_trailing_id(self):
        name = SOURCE._build_name({"title": "X-T50 body Charcoal Silver (16828375)", "vendor": {"title": "Fujifilm"}})

        self.assertEqual(name, "Fujifilm X-T50 body Charcoal Silver")

    def test_build_name_does_not_repeat_a_vendor_already_in_the_title(self):
        name = SOURCE._build_name({"title": "Fujifilm X-T50 body Silver (16828284)", "vendor": {"title": "Fujifilm"}})

        self.assertEqual(name, "Fujifilm X-T50 body Silver")

    def test_build_name_without_a_vendor_keeps_the_title(self):
        name = SOURCE._build_name({"title": "GREE Pular Inverter GWH12AGB-K6DNA1B", "vendor": None})

        self.assertEqual(name, "GREE Pular Inverter GWH12AGB-K6DNA1B")


class ToOfferTestCase(TestCase):
    def test_to_offer_maps_a_new_offer_with_its_shop_reputation(self):
        offer = SOURCE._to_offer(
            {
                "firmId": 862,
                "firmTitle": "ALLO.ua",
                "price": 59500,
                "conditionId": 0,
                "_id": 14183793988,
                "firmExtraInfo": {"rating": 74, "reviewsCountAllPeriod": 9338, "isOfficial": True},
            }
        )

        self.assertEqual(offer.firm_id, 862)
        self.assertEqual(offer.shop, "ALLO.ua")
        self.assertEqual(offer.price, 59500)
        self.assertEqual(offer.rating, 74)
        self.assertEqual(offer.reviews, 9338)
        self.assertTrue(offer.is_official)
        self.assertTrue(offer.is_new)
        self.assertEqual(offer.offer_id, 14183793988)

    def test_to_offer_marks_a_used_offer_as_not_new(self):
        offer = SOURCE._to_offer({"firmId": 1, "firmTitle": "X", "price": 48000, "conditionId": 1, "firmExtraInfo": {}})

        self.assertFalse(offer.is_new)
        self.assertIsNone(offer.rating)

    def test_to_offer_skips_a_node_missing_a_price(self):
        offer = SOURCE._to_offer({"firmId": 1, "firmTitle": "X", "price": None, "conditionId": 0})

        self.assertIsNone(offer)
