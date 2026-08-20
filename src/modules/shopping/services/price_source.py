from typing import Protocol
from urllib.parse import urlparse

from src.modules.shopping.domain import TrackedProduct

HOTLINE_HOST = "hotline.ua"


def is_hotline_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    return parsed.scheme in ("http", "https") and parsed.netloc.removeprefix("www.") == HOTLINE_HOST


class PriceSource(Protocol):
    """Reads a product's name and current lowest price off a price-comparison page"""

    async def fetch(self, url: str) -> TrackedProduct | None:
        ...
