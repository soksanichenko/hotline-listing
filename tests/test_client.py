"""Tests for the hotline.ua GraphQL/scraping client."""

import httpx
import pytest
from hotline_prices.client import extract_path, fetch_chart, fetch_offer_prices


@pytest.mark.parametrize(
    "url,expected",
    [
        (
            "https://hotline.ua/ua/computer-monitory/alienware-aw3426dwm-210-bwpz/",
            "alienware-aw3426dwm-210-bwpz",
        ),
        (
            "https://hotline.ua/computer-monitory/alienware-aw3426dwm-210-bwpz/",
            "alienware-aw3426dwm-210-bwpz",
        ),
        ("https://hotline.ua/ua/computer-monitory/some-slug", "some-slug"),
        ("https://hotline.ua/ua/computer-monitory/some-slug?utm_source=x", "some-slug"),
        ("https://hotline.ua/ua/computer-monitory/some-slug#section", "some-slug"),
    ],
)
def test_extract_path_matches_known_url_shapes(url, expected):
    assert extract_path(url) == expected


def test_extract_path_falls_back_to_stripped_input_when_no_match():
    assert extract_path("not-a-hotline-url/") == "not-a-hotline-url"


@pytest.mark.asyncio
async def test_fetch_chart_returns_chart_payload():
    chart = {
        "priceUAH": [["27.09.2026", 100]],
        "minPriceUAH": [],
        "priceUSD": [],
        "quantity": [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"chart": chart}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_chart(client, "some-slug")
    assert result == chart


@pytest.mark.asyncio
async def test_fetch_chart_raises_on_graphql_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"errors": [{"message": "boom"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError):
            await fetch_chart(client, "some-slug")


@pytest.mark.asyncio
async def test_fetch_chart_raises_on_http_error_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server error")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_chart(client, "some-slug")


_OFFERS_HTML = (
    "<html><body><script>window.__NUXT__=(function(a,b){return "
    "{state:{product:{offers:{edges:[{node:{price:a}},{node:{price:b}}]}}}}}"
    "})(111,222);</script></body></html>"
)


@pytest.mark.asyncio
async def test_fetch_offer_prices_parses_page_html():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_OFFERS_HTML)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        prices = await fetch_offer_prices(
            client, "https://hotline.ua/ua/cat/some-slug/"
        )
    assert prices == [111.0, 222.0]


@pytest.mark.asyncio
async def test_fetch_offer_prices_raises_on_http_error_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_offer_prices(client, "https://hotline.ua/ua/cat/some-slug/")
