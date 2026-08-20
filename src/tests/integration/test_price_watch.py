from datetime import timedelta

from src.common.domain import Actor
from src.common.exceptions import DoesNotExistError, ValidationError
from src.modules.shopping.commands import TrackExistingItemCommand, TrackShoppingItemCommand
from src.modules.shopping.constants import PriceTrend, ShoppingHorizon
from src.modules.shopping.services.shopping_list_reader import load_priced_shopping_list
from src.modules.shopping.use_cases.check_tracked_prices import CheckTrackedPricesUseCase
from src.modules.shopping.use_cases.track_existing_item import TrackExistingItemUseCase
from src.modules.shopping.use_cases.track_shopping_item import TrackShoppingItemUseCase
from src.tests.fakes import ScriptedPriceSource
from src.tests.integration.base import FROZEN_NOW, BaseIntegrationTestCase

BOHDAN = Actor(telegram_user_id=2, display_name="Богдан")
PRODUCT_URL = "https://hotline.ua/ua/mobile-x/dyson-v15/"


class TrackShoppingItemTestCase(BaseIntegrationTestCase):
    def track(self, source: ScriptedPriceSource):
        return TrackShoppingItemUseCase(uow=self.uow, actor=BOHDAN, price_source=source, checked_at=FROZEN_NOW)

    async def test_track_shopping_item_adds_it_to_the_someday_list_with_its_current_price(self):
        source = ScriptedPriceSource({PRODUCT_URL: [21999]}, name="Пилосос Dyson V15")

        shopping_list = await self.track(source)(TrackShoppingItemCommand(hotline_url=PRODUCT_URL))

        self.assertEqual(shopping_list.needed_now, [])
        self.assertEqual(len(shopping_list.wanted_later), 1)
        item = shopping_list.wanted_later[0]
        self.assertEqual(item.name, "Пилосос Dyson V15")
        self.assertEqual(item.current_price, 21999)
        self.assertEqual(item.initial_price, 21999)
        self.assertTrue(item.is_tracked)

    async def test_track_shopping_item_shortens_a_very_long_hotline_name(self):
        long_name = "Смартфон Apple iPhone 17 256GB Black (MG6J4) з дуже довгою назвою для списку покупок"
        source = ScriptedPriceSource({PRODUCT_URL: [39199]}, name=long_name)

        shopping_list = await self.track(source)(TrackShoppingItemCommand(hotline_url=PRODUCT_URL))

        self.assertTrue(shopping_list.wanted_later[0].name.endswith("…"))
        self.assertLessEqual(len(shopping_list.wanted_later[0].name), 64)

    async def test_track_shopping_item_that_is_already_tracked_does_not_duplicate_it(self):
        source = ScriptedPriceSource({PRODUCT_URL: [21999, 20500]}, name="Dyson")
        await self.track(source)(TrackShoppingItemCommand(hotline_url=PRODUCT_URL))

        shopping_list = await self.track(source)(TrackShoppingItemCommand(hotline_url=PRODUCT_URL))

        self.assertEqual(len(shopping_list.wanted_later), 1)
        self.assertEqual(shopping_list.wanted_later[0].current_price, 21999)

    async def test_track_shopping_item_with_a_non_hotline_link_raises_validation_error(self):
        source = ScriptedPriceSource({})

        with self.assertRaises(ValidationError) as context:
            await self.track(source)(TrackShoppingItemCommand(hotline_url="https://rozetka.com.ua/dyson/"))

        self.assertEqual(str(context.exception), "Only hotline.ua links can be tracked")

    async def test_track_shopping_item_whose_page_cannot_be_read_raises_validation_error(self):
        source = ScriptedPriceSource({PRODUCT_URL: [None]})

        with self.assertRaises(ValidationError) as context:
            await self.track(source)(TrackShoppingItemCommand(hotline_url=PRODUCT_URL))

        self.assertEqual(str(context.exception), "Could not read the product page")


class TrackExistingItemTestCase(BaseIntegrationTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with self.uow as uow:
            item = await uow.shopping_items.create(
                {
                    "name": "пилосос",
                    "horizon": ShoppingHorizon.LATER,
                    "added_by_telegram_user_id": 2,
                    "added_by_display_name": "Богдан",
                }
            )
            self.item_id = item.id

    def track_existing(self, source: ScriptedPriceSource):
        return TrackExistingItemUseCase(uow=self.uow, price_source=source, checked_at=FROZEN_NOW)

    async def test_track_existing_item_keeps_the_family_name_and_attaches_the_price(self):
        source = ScriptedPriceSource({PRODUCT_URL: [21999]}, name="Пилосос Dyson V15 Detect")

        product = await self.track_existing(source)(
            TrackExistingItemCommand(item_id=self.item_id, hotline_url=PRODUCT_URL)
        )

        self.assertEqual(product.price, 21999)
        async with self.uow as uow:
            shopping_list = await load_priced_shopping_list(uow)
        item = shopping_list.wanted_later[0]
        self.assertEqual(item.name, "пилосос")
        self.assertEqual(item.current_price, 21999)
        self.assertTrue(item.is_tracked)

    async def test_track_existing_item_that_is_gone_raises_does_not_exist(self):
        source = ScriptedPriceSource({PRODUCT_URL: [21999]})

        with self.assertRaises(DoesNotExistError) as context:
            await self.track_existing(source)(TrackExistingItemCommand(item_id=999, hotline_url=PRODUCT_URL))

        self.assertEqual(str(context.exception), "Shopping item 999 not found")

    async def test_track_existing_item_with_an_unreadable_page_raises_validation_error(self):
        source = ScriptedPriceSource({PRODUCT_URL: [None]})

        with self.assertRaises(ValidationError) as context:
            await self.track_existing(source)(TrackExistingItemCommand(item_id=self.item_id, hotline_url=PRODUCT_URL))

        self.assertEqual(str(context.exception), "Could not read the product page")


class CheckTrackedPricesTestCase(BaseIntegrationTestCase):
    async def track(self, url: str, price: int, name: str = "Dyson"):
        source = ScriptedPriceSource({url: [price]}, name=name)
        await TrackShoppingItemUseCase(uow=self.uow, actor=BOHDAN, price_source=source, checked_at=FROZEN_NOW)(
            TrackShoppingItemCommand(hotline_url=url)
        )

    async def check(self, source: ScriptedPriceSource, at=None):
        return await CheckTrackedPricesUseCase(
            uow=self.uow, price_source=source, checked_at=at or FROZEN_NOW + timedelta(days=1)
        )()

    async def test_check_tracked_prices_announces_a_drop_to_a_new_low(self):
        await self.track(PRODUCT_URL, 21999, name="Пилосос Dyson")

        outcome = await self.check(ScriptedPriceSource({PRODUCT_URL: [19500]}))

        self.assertEqual(len(outcome.drops), 1)
        drop = outcome.drops[0]
        self.assertEqual(drop.name, "Пилосос Dyson")
        self.assertEqual(drop.previous_low, 21999)
        self.assertEqual(drop.new_price, 19500)
        self.assertEqual(drop.hotline_url, PRODUCT_URL)

    async def test_check_tracked_prices_carries_the_reputable_shop_into_the_drop(self):
        await self.track(PRODUCT_URL, 21999, name="Пилосос Dyson")

        outcome = await self.check(
            ScriptedPriceSource(
                {PRODUCT_URL: [19500]},
                shop="Rozetka",
                rating=96,
                buy_link="https://hotline.ua/go/price/555/",
            )
        )

        drop = outcome.drops[0]
        self.assertEqual(drop.shop, "Rozetka")
        self.assertEqual(drop.rating, 96)
        self.assertEqual(drop.buy_link, "https://hotline.ua/go/price/555/")

    async def test_check_tracked_prices_stays_silent_when_the_price_rises(self):
        await self.track(PRODUCT_URL, 21999)

        outcome = await self.check(ScriptedPriceSource({PRODUCT_URL: [22500]}))

        self.assertEqual(outcome.drops, [])
        self.assertEqual(outcome.failures, [])

    async def test_check_tracked_prices_stays_silent_when_the_price_is_unchanged(self):
        await self.track(PRODUCT_URL, 21999)

        outcome = await self.check(ScriptedPriceSource({PRODUCT_URL: [21999]}))

        self.assertEqual(outcome.drops, [])

    async def test_check_tracked_prices_only_announces_below_the_lowest_ever_seen(self):
        await self.track(PRODUCT_URL, 21999)
        # a dip to 19500 sets a new floor; a later 20000 is cheaper than the start but not a new low
        await self.check(ScriptedPriceSource({PRODUCT_URL: [19500]}), at=FROZEN_NOW + timedelta(days=1))

        outcome = await self.check(ScriptedPriceSource({PRODUCT_URL: [20000]}), at=FROZEN_NOW + timedelta(days=2))

        self.assertEqual(outcome.drops, [])

    async def test_check_tracked_prices_reports_a_page_it_could_not_read_as_a_failure(self):
        await self.track(PRODUCT_URL, 21999, name="Dyson")

        outcome = await self.check(ScriptedPriceSource({PRODUCT_URL: [None]}))

        self.assertEqual(outcome.drops, [])
        self.assertEqual(outcome.failures, ["Dyson"])

    async def test_check_tracked_prices_ignores_plain_items_without_a_link(self):
        source = ScriptedPriceSource({})
        async with self.uow as uow:
            await uow.shopping_items.create(
                {
                    "name": "олія",
                    "horizon": ShoppingHorizon.NOW,
                    "added_by_telegram_user_id": 1,
                    "added_by_display_name": "Марта",
                }
            )

        outcome = await self.check(source)

        self.assertEqual(source.fetched_urls, [])
        self.assertEqual(outcome.drops, [])

    async def test_check_tracked_prices_keeps_the_trend_arrow_pointing_at_the_first_price(self):
        await self.track(PRODUCT_URL, 21999)
        await self.check(ScriptedPriceSource({PRODUCT_URL: [19500]}))

        async with self.uow as uow:
            from src.modules.shopping.services.shopping_list_reader import load_priced_shopping_list

            shopping_list = await load_priced_shopping_list(uow)

        item = shopping_list.wanted_later[0]
        self.assertEqual(item.current_price, 19500)
        self.assertEqual(item.initial_price, 21999)
        self.assertEqual(item.price_trend, PriceTrend.DOWN)
