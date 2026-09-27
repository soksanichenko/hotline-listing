"""Tests for hotline_prices.app's price-fetching logic: _get_product,
_get_offer_prices, _check_price_alerts. Calls these directly (not via
TestClient HTTP requests) — see tests/test_app_routes.py for route coverage."""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

from hotline_prices.config import ProductConfig
from hotline_prices.db import config_create, configs_list_with_owner_email


def _nuxt_html(prices: list[float]) -> str:
    params = ",".join(chr(ord("a") + i) for i in range(len(prices)))
    edges = ",".join(
        f"{{node:{{price:{chr(ord('a') + i)}}}}}" for i in range(len(prices))
    )
    args = ",".join(str(p) for p in prices)
    return (
        "<html><body><script>window.__NUXT__=(function("
        f"{params}){{return {{state:{{product:{{offers:{{edges:[{edges}]}}}}}}}}}})"
        f"({args});</script></body></html>"
    )


async def test_get_product_happy_path(client, fake_hotline, app_module):
    fake_hotline.set_chart(
        "some-slug",
        {
            "priceUAH": [[datetime.now(UTC).strftime("%d.%m.%Y"), 12000]],
            "minPriceUAH": [[datetime.now(UTC).strftime("%d.%m.%Y"), 11000]],
            "priceUSD": [[datetime.now(UTC).strftime("%d.%m.%Y"), 300]],
            "quantity": [[datetime.now(UTC).strftime("%d.%m.%Y"), 4]],
        },
    )
    summary = await app_module._get_product(
        ProductConfig(url="https://hotline.ua/ua/cat/some-slug/")
    )
    assert summary.error is None
    assert summary.price_uah == 12000
    assert summary.price_usd == 300
    assert summary.quantity == 4
    assert summary.min_price_uah == 11000
    assert summary.price_history_uah == [12000]


async def test_get_product_fetch_chart_error(
    client, fake_hotline, app_module, monkeypatch
):
    async def _raise(*_args, **_kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(app_module, "fetch_chart", _raise)
    summary = await app_module._get_product(
        ProductConfig(url="https://hotline.ua/ua/cat/some-slug/")
    )
    assert summary.error == "boom"
    assert summary.price_uah == 0
    assert summary.min_price_uah == 0


async def test_get_product_stale_fallback_with_offers(client, fake_hotline, app_module):
    old = (datetime.now(UTC) - timedelta(days=10)).strftime("%d.%m.%Y")
    fake_hotline.set_chart(
        "some-slug", {"priceUAH": [[old, 12000]], "priceUSD": [], "quantity": []}
    )
    url = "https://hotline.ua/ua/cat/some-slug/"
    fake_hotline.set_page_html(url, _nuxt_html([19000, 21000]))

    summary = await app_module._get_product(ProductConfig(url=url))
    assert summary.error is None
    assert summary.price_uah == 20000
    assert summary.min_price_uah == 19000
    assert summary.quantity == 2


async def test_get_product_stale_fallback_without_offers(
    client, fake_hotline, app_module
):
    old = (datetime.now(UTC) - timedelta(days=10)).strftime("%d.%m.%Y")
    fake_hotline.set_chart(
        "some-slug", {"priceUAH": [[old, 12000]], "priceUSD": [], "quantity": []}
    )
    summary = await app_module._get_product(
        ProductConfig(url="https://hotline.ua/ua/cat/some-slug/")
    )
    assert summary.error == f"Ціна застаріла (з {old})"
    assert summary.stale_since == old
    assert summary.price_uah == 0


async def test_get_offer_prices_caches(client, fake_hotline, app_module):
    url = "https://hotline.ua/ua/cat/some-slug/"
    fake_hotline.set_page_html(url, _nuxt_html([19000]))
    first = await app_module._get_offer_prices("some-slug", url)
    fake_hotline.set_page_html(
        url, _nuxt_html([1])
    )  # would change the result if not cached
    second = await app_module._get_offer_prices("some-slug", url)
    assert first == second == [19000.0]


async def test_check_price_alerts_above_target_no_email(
    client, fake_hotline, app_module, monkeypatch
):
    send_mock = Mock()
    monkeypatch.setattr(app_module, "send_price_alert", send_mock)
    url = "https://hotline.ua/ua/cat/expensive/"
    fake_hotline.set_page_html(url, _nuxt_html([50000]))
    await config_create(
        {"products": [{"url": url, "count": 1, "target_price": 20000}]},
        owner_discord_email="buyer@example.com",
    )

    await app_module._check_price_alerts()

    send_mock.assert_not_called()


async def test_check_price_alerts_state_machine(
    client, fake_hotline, fake_redis, app_module, monkeypatch
):
    send_mock = Mock()
    monkeypatch.setattr(app_module, "send_price_alert", send_mock)
    url = "https://hotline.ua/ua/cat/watched/"
    config_id = await config_create(
        {"products": [{"url": url, "count": 1, "target_price": 20000}]},
        owner_discord_email="buyer@example.com",
    )

    async def alert_state_for(cid):
        rows = await configs_list_with_owner_email()
        return next(r["alert_state"] for r in rows if r["id"] == cid)

    async def set_price_and_check(price: float) -> None:
        # _get_offer_prices caches per product path — flush so each step
        # sees the new price, simulating the cache having expired by the
        # next scheduled _check_price_alerts run.
        await fake_redis.flushall()
        fake_hotline.set_page_html(url, _nuxt_html([price]))
        await app_module._check_price_alerts()

    # price above target: stays armed, no email
    await set_price_and_check(50000)
    send_mock.assert_not_called()

    # price drops to/below target: sends once, disarms
    await set_price_and_check(19000)
    send_mock.assert_called_once()
    assert send_mock.call_args.args[3] == 19000
    state = await alert_state_for(config_id)
    assert state[url]["armed"] is False
    assert state[url]["last_notified_price"] == 19000

    # still below target, already disarmed: stays silent
    send_mock.reset_mock()
    await set_price_and_check(19000)
    send_mock.assert_not_called()

    # price rises back above target: re-arms
    await set_price_and_check(50000)
    send_mock.assert_not_called()
    state = await alert_state_for(config_id)
    assert state[url]["armed"] is True

    # dips again after re-arming: notifies again
    await set_price_and_check(18000)
    send_mock.assert_called_once()
