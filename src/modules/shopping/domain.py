from src.common.domain import DomainModel
from src.infrastructure.db.models import ShoppingItem
from src.modules.shopping.constants import PriceTrend, ShoppingHorizon


class ShopOffer(DomainModel):
    """One shop's offer for a product, as decoded from a price-comparison page"""

    firm_id: int
    shop: str
    price: int
    rating: int | None = None
    reviews: int | None = None
    is_official: bool = False
    is_new: bool = True
    offer_id: int | None = None

    def is_reputable(self, policy: "ReputabilityPolicy") -> bool:
        if not self.is_new:
            return False
        if self.firm_id in policy.trusted_firm_ids:
            return True
        return (
            self.rating is not None
            and self.rating >= policy.minimum_rating
            and self.reviews is not None
            and self.reviews >= policy.minimum_reviews
        )


class ReputabilityPolicy(DomainModel):
    # a shop counts as reputable if it clears the rating+reviews bar OR sits in the trusted allowlist — either way
    minimum_rating: int
    minimum_reviews: int
    trusted_firm_ids: frozenset[int] = frozenset()


class TrackedProduct(DomainModel):
    """The reputable price a source reads off a product page, plus the context an alert needs"""

    name: str
    # the tracked value: cheapest reputable offer, or the absolute-cheapest new one when none clears the bar
    price: int
    # the absolute cheapest of all, kept as a "something ultra-cheap appeared" tripwire and drift check
    naive_minimum: int | None = None
    is_reputable: bool = True
    shop: str | None = None
    rating: int | None = None
    buy_link: str | None = None


def build_tracked_product(
    name: str, offers: list[ShopOffer], naive_minimum: int, policy: ReputabilityPolicy
) -> TrackedProduct:
    reputable = [offer for offer in offers if offer.is_reputable(policy)]
    if reputable:
        pick = min(reputable, key=lambda offer: offer.price)
        return _tracked_from(name, pick, naive_minimum, is_reputable=True)

    # nobody cleared the bar — track the cheapest new offer instead, flagged so the alert can say so
    new_offers = [offer for offer in offers if offer.is_new]
    if not new_offers:
        return TrackedProduct(name=name, price=naive_minimum, naive_minimum=naive_minimum, is_reputable=False)
    return _tracked_from(name, min(new_offers, key=lambda offer: offer.price), naive_minimum, is_reputable=False)


def _tracked_from(name: str, offer: ShopOffer, naive_minimum: int, is_reputable: bool) -> TrackedProduct:
    return TrackedProduct(
        name=name,
        price=offer.price,
        naive_minimum=naive_minimum,
        is_reputable=is_reputable,
        shop=offer.shop,
        rating=offer.rating,
        buy_link=f"https://hotline.ua/go/price/{offer.offer_id}/" if offer.offer_id else None,
    )


class ShoppingItemDetails(DomainModel):
    id: int
    name: str
    horizon: ShoppingHorizon
    added_by_display_name: str
    photo_telegram_file_id: str | None = None
    note: str | None = None
    current_price: int | None = None
    initial_price: int | None = None

    @classmethod
    def from_item(cls, item: ShoppingItem, current_price: int | None = None, initial_price: int | None = None):
        return cls(
            id=item.id,
            name=item.name,
            horizon=ShoppingHorizon(item.horizon),
            added_by_display_name=item.added_by_display_name,
            photo_telegram_file_id=item.photo_telegram_file_id,
            note=item.note,
            current_price=current_price,
            initial_price=initial_price,
        )

    @property
    def is_tracked(self) -> bool:
        return self.current_price is not None

    @property
    def has_photo(self) -> bool:
        return self.photo_telegram_file_id is not None

    @property
    def has_note(self) -> bool:
        return bool(self.note and self.note.strip())

    @property
    def price_trend(self) -> PriceTrend:
        # the arrow is against the price at tracking time, so it reads "cheaper than when I added it"
        if self.current_price is None or self.initial_price is None or self.current_price == self.initial_price:
            return PriceTrend.FLAT
        return PriceTrend.DOWN if self.current_price < self.initial_price else PriceTrend.UP


class PriceDropAnnouncement(DomainModel):
    """A tracked item reached a new low since watching began — what the alert renders from"""

    name: str
    hotline_url: str
    previous_low: int
    new_price: int
    shop: str | None = None
    rating: int | None = None
    buy_link: str | None = None


class PriceCheckOutcome(DomainModel):
    drops: list[PriceDropAnnouncement]
    # names of items whose page could not be read this round — the sign a parser or the site broke
    failures: list[str]


class ShoppingList(DomainModel):
    needed_now: list[ShoppingItemDetails]
    wanted_later: list[ShoppingItemDetails]

    @classmethod
    def from_items(
        cls,
        items: list[ShoppingItem],
        current_prices: dict[int, int] | None = None,
        initial_prices: dict[int, int] | None = None,
    ) -> "ShoppingList":
        current_prices = current_prices or {}
        initial_prices = initial_prices or {}
        details = [
            ShoppingItemDetails.from_item(item, current_prices.get(item.id), initial_prices.get(item.id))
            for item in items
        ]
        return cls(
            needed_now=[item for item in details if item.horizon == ShoppingHorizon.NOW],
            wanted_later=[item for item in details if item.horizon == ShoppingHorizon.LATER],
        )

    @property
    def is_empty(self) -> bool:
        return not self.needed_now and not self.wanted_later
