"""Async GraphQL client for hotline.ua."""

import re

import httpx

from .nuxt_parser import extract_offer_prices

_GRAPHQL_URL = "https://hotline.ua/svc/frontend-api/graphql"
_BASE_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0",
    "x-language": "uk",
    "Origin": "https://hotline.ua",
}

_CHART_QUERY = (
    "query getChart($path: String!) {"
    "  chart(productPath: $path) { priceUAH minPriceUAH priceUSD quantity }"
    "}"
)


def extract_path(url: str) -> str:
    """Extract product path slug from a full hotline.ua URL."""
    match = re.search(r"hotline\.ua/(?:ua/)?[^/]+/([^/?#]+)", url)
    return match.group(1) if match else url.strip("/")


async def fetch_chart(client: httpx.AsyncClient, path: str) -> dict:
    """Return raw chart payload: {priceUAH, minPriceUAH, priceUSD, quantity}."""
    r = await client.post(
        _GRAPHQL_URL,
        json={
            "operationName": "getChart",
            "variables": {"path": path},
            "query": _CHART_QUERY,
        },
        headers={**_BASE_HEADERS, "x-referer": f"https://hotline.ua/ua/{path}/"},
    )
    r.raise_for_status()
    body = r.json()
    if errors := body.get("errors"):
        raise ValueError(errors)
    return body["data"]["chart"]


async def fetch_offer_prices(client: httpx.AsyncClient, url: str) -> list[float]:
    """Return per-seller offer prices scraped from the plain product page.

    hotline.ua only exposes the per-seller offer list (as opposed to
    getChart's priceUAH/minPriceUAH aggregates) via an authenticated GraphQL
    query — but the same data is already embedded, unauthenticated, in the
    product page's Nuxt SSR payload. See nuxt_parser.extract_offer_prices.
    """
    r = await client.get(url, headers={"User-Agent": _BASE_HEADERS["User-Agent"]})
    r.raise_for_status()
    return extract_offer_prices(r.text)
