"""What a call to each model costs, so spending can be counted in money rather than in tokens."""

from dataclasses import dataclass

# dollars per million tokens, from claude.com/pricing — read 2026-10-08. a model missing from here is
# charged at the dearest rate below rather than at nothing: an unknown model must not look free, or a typo
# in a setting would silently switch the guard off
MICRO_USD_PER_USD = 1_000_000
TOKENS_PER_PRICED_UNIT = 1_000_000


@dataclass(frozen=True)
class ModelPrice:
    input_usd_per_million: float
    output_usd_per_million: float


MODEL_PRICES: dict[str, ModelPrice] = {
    "claude-fable-5-1": ModelPrice(10.0, 50.0),
    "claude-opus-5-5": ModelPrice(4.0, 20.0),
    "claude-sonnet-5-5": ModelPrice(2.0, 10.0),
    "claude-haiku-4-5-20251001": ModelPrice(0.10, 0.50),
}
DEAREST_PRICE = max(MODEL_PRICES.values(), key=lambda price: price.output_usd_per_million)


def price_of(model: str, input_tokens: int, output_tokens: int) -> int:
    """What this call cost, in millionths of a dollar — an integer, because money must not drift."""
    price = MODEL_PRICES.get(model, DEAREST_PRICE)
    dollars = (
        input_tokens * price.input_usd_per_million + output_tokens * price.output_usd_per_million
    ) / TOKENS_PER_PRICED_UNIT
    return round(dollars * MICRO_USD_PER_USD)
