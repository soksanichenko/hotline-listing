"""Async GraphQL client for hotline.ua."""

import re

import httpx

_GRAPHQL_URL = 'https://hotline.ua/svc/frontend-api/graphql'
_BASE_HEADERS = {
    'Content-Type': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0',
    'x-language': 'uk',
    'Origin': 'https://hotline.ua',
}

_CHART_QUERY = (
    'query getChart($path: String!) {'
    '  chart(productPath: $path) { priceUAH priceUSD quantity }'
    '}'
)


def extract_path(url: str) -> str:
    """Extract product path slug from a full hotline.ua URL."""
    match = re.search(r'hotline\.ua/(?:ua/)?[^/]+/([^/?#]+)', url)
    return match.group(1) if match else url.strip('/')


async def fetch_chart(client: httpx.AsyncClient, path: str) -> dict:
    """Return raw chart payload: {priceUAH, priceUSD, quantity}."""
    r = await client.post(
        _GRAPHQL_URL,
        json={'operationName': 'getChart', 'variables': {'path': path}, 'query': _CHART_QUERY},
        headers={**_BASE_HEADERS, 'x-referer': f'https://hotline.ua/ua/{path}/'},
    )
    r.raise_for_status()
    body = r.json()
    if errors := body.get('errors'):
        raise ValueError(errors)
    return body['data']['chart']
