import asyncio
import json
import logging
import re

import aiohttp
import dukpy

from src.modules.shopping.domain import ReputabilityPolicy, ShopOffer, TrackedProduct, build_tracked_product

logger = logging.getLogger(__name__)

# a plain browser user agent; hotline serves the same content to any client, the guard is the token below
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT_SECONDS = 20
HOTLINE_ORIGIN = "https://hotline.ua"
GRAPHQL_ENDPOINT = "https://hotline.ua/svc/frontend-api/graphql"

# hotline's product pages are now a client-rendered spa fed by this graphql api; a plain fetch of a product page
# return a "legacy controller disabled" stub while they roll the new frontend out section by section. the api
# needs a per-request token that only a *product* page mints (category tokens are rejected), so we lift one from a
# live product found under a stable category and reuse it for every tracked item in a run — it survives reuse
NUXT_PATTERN = re.compile(r"<script[^>]*>\s*(window\.__NUXT__=.*?)</script>", re.DOTALL)
NUXT_STUBS = "var window={},document={},navigator={},location={};"
# a product url is /ua/<hyphen-joined-category>/<slug>/ — two segments, unlike the slashed nav/category links
PRODUCT_LINK_PATTERN = re.compile(r'href="(/ua/[a-z0-9]+-[a-z0-9-]+/[a-z0-9-]*[a-z][a-z0-9-]*/)"')
# hotline suffixes a bare product title with its numeric id, e.g. "X-T50 body Silver (16828284)"
TRAILING_ID_PATTERN = re.compile(r"\s*\(\d+\)\s*$")

PRODUCT_QUERY = (
    "query trackedProduct($path: String!, $cityId: Int!) {"
    "  byPathQueryProduct(path: $path, cityId: $cityId) {"
    "    title vendor { title }"
    "    offers(first: 1000) { edges { node { firmId firmTitle price conditionId firmExtraInfo _id } } }"
    "  }"
    "}"
)


class HotlineTokenError(Exception):
    """A working product token could not be minted — the donor category or product page did not yield one"""


class HotlinePriceSource:
    def __init__(self, policy: ReputabilityPolicy, donor_category_url: str, city_id: int = 187):
        self.policy = policy
        self.donor_category_url = donor_category_url
        self.city_id = city_id
        # (token, request_id, referer) reused across every item in a run; re-minted on expiry
        self._credentials: tuple[str, str, str] | None = None

    async def fetch(self, url: str) -> TrackedProduct | None:
        slug = self._extract_slug(url)
        if slug is None:
            return None

        try:
            product = await self._query_product(slug)
        except aiohttp.ClientError:
            logger.warning("Could not reach hotline for %s", url, exc_info=True)
            return None
        except HotlineTokenError:
            logger.warning("Could not mint a hotline api token for %s", url)
            return None

        if product is None:
            return None
        offers = [offer for offer in map(self._to_offer, self._offer_nodes(product)) if offer is not None]
        if not offers:
            logger.warning("Hotline returned no offers for %s", url)
            return None

        naive_minimum = min(offer.price for offer in offers)
        return build_tracked_product(self._build_name(product), offers, naive_minimum, self.policy)

    async def _query_product(self, slug: str) -> dict | None:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)) as session:
            # one retry: a token cached from a previous run may have expired between daily checks
            for _ in range(2):
                token, request_id, referer = await self._ensure_credentials(session)
                headers = {
                    "User-Agent": BROWSER_USER_AGENT,
                    "x-token": token,
                    "x-request-id": request_id,
                    "x-referer": referer,
                    "x-language": "uk",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                }
                payload = {"query": PRODUCT_QUERY, "variables": {"path": slug, "cityId": self.city_id}}
                async with session.post(GRAPHQL_ENDPOINT, headers=headers, json=payload) as response:
                    body = await response.json(content_type=None)

                errors = body.get("errors") or []
                if any(error.get("message") == "invalid-request-token" for error in errors):
                    self._credentials = None
                    continue
                if errors:
                    logger.warning("Hotline graphql error for %s: %s", slug, errors[0].get("message"))
                    return None
                return (body.get("data") or {}).get("byPathQueryProduct")
        raise HotlineTokenError(slug)

    async def _ensure_credentials(self, session: aiohttp.ClientSession) -> tuple[str, str, str]:
        if self._credentials is not None:
            return self._credentials

        donor_url = await self._discover_donor_product(session)
        state = (await self._read_nuxt_state(session, donor_url)).get("state") or {}
        token = (state.get("pageType") or {}).get("token")
        request_id = state.get("uniqId")
        if not token or not request_id:
            raise HotlineTokenError(donor_url)
        self._credentials = (token, request_id, donor_url)
        return self._credentials

    async def _discover_donor_product(self, session: aiohttp.ClientSession) -> str:
        html = await self._download_text(session, self.donor_category_url)
        match = PRODUCT_LINK_PATTERN.search(html)
        if match is None:
            raise HotlineTokenError(self.donor_category_url)
        return HOTLINE_ORIGIN + match.group(1)

    async def _read_nuxt_state(self, session: aiohttp.ClientSession, url: str) -> dict:
        html = await self._download_text(session, url)
        match = NUXT_PATTERN.search(html)
        if match is None:
            raise HotlineTokenError(url)
        script = match.group(1).strip().rstrip(";")
        return await asyncio.get_running_loop().run_in_executor(None, self._decode_nuxt, script)

    async def _download_text(self, session: aiohttp.ClientSession, url: str) -> str:
        async with session.get(url, headers={"User-Agent": BROWSER_USER_AGENT, "Accept-Language": "uk"}) as response:
            return await response.text()

    @staticmethod
    def _decode_nuxt(script: str) -> dict:
        return json.loads(dukpy.evaljs(NUXT_STUBS + script + ";JSON.stringify(window.__NUXT__)"))

    def _offer_nodes(self, product: dict) -> list:
        return [edge.get("node") for edge in ((product.get("offers") or {}).get("edges") or [])]

    def _to_offer(self, node) -> ShopOffer | None:
        if not isinstance(node, dict) or node.get("price") is None or node.get("firmId") is None:
            return None
        extra = node.get("firmExtraInfo") or {}
        return ShopOffer(
            firm_id=node["firmId"],
            shop=node.get("firmTitle") or "",
            price=int(node["price"]),
            rating=extra.get("rating"),
            reviews=extra.get("reviewsCountAllPeriod"),
            is_official=bool(extra.get("isOfficial")),
            is_new=node.get("conditionId") == 0,
            offer_id=node.get("_id"),
        )

    def _extract_slug(self, url: str) -> str | None:
        return url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1] or None

    def _build_name(self, product: dict) -> str:
        title = (product.get("title") or "").strip()
        vendor = ((product.get("vendor") or {}).get("title") or "").strip()
        if vendor and not title.lower().startswith(vendor.lower()):
            title = f"{vendor} {title}"
        return TRAILING_ID_PATTERN.sub("", title).strip()
