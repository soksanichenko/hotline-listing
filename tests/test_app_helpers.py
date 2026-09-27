"""Tests for the pure/private helper functions in hotline_prices.app."""

from datetime import UTC, datetime, timedelta


def test_parse_hotline_date_valid(app_module):
    assert app_module._parse_hotline_date("27.09.2026") == "2026-09-27"


def test_parse_hotline_date_malformed(app_module):
    assert app_module._parse_hotline_date("not-a-date") == "not-a-date"


def test_normalize_series(app_module):
    series = [["27.09.2026", 100], ["28.09.2026", 200]]
    assert app_module._normalize_series(series) == [
        ["2026-09-27", 100],
        ["2026-09-28", 200],
    ]


def test_slug_to_title(app_module):
    assert app_module._slug_to_title("apple-iphone-15") == "Apple Iphone 15"


def test_sparkline_too_short(app_module):
    assert app_module._sparkline([]) == ""
    assert app_module._sparkline([100]) == ""


def test_sparkline_shape(app_module):
    result = app_module._sparkline([100, 200, 150])
    points = result.split(" ")
    assert len(points) == 3
    for point in points:
        x, y = point.split(",")
        float(x)
        float(y)


def test_sparkline_flat_series_no_div_by_zero(app_module):
    # mn == mx would make `rng` 0 without the `or 1` guard — must not raise.
    result = app_module._sparkline([100, 100, 100])
    points = result.split(" ")
    assert len(points) == 3


def test_fmt_uah(app_module):
    # the thousands separator is a non-breaking space (U+00A0), not a plain one
    assert app_module._fmt_uah(12345) == "12\xa0345 ₴"
    assert app_module._fmt_uah(999) == "999 ₴"


def test_fmt_usd(app_module):
    assert app_module._fmt_usd(1234.5) == "$1,234.50"
    assert app_module._fmt_usd(99.9) == "$99.90"


def test_chart_stale_since_empty_series(app_module):
    assert app_module._chart_stale_since([]) == "—"


def test_chart_stale_since_recent(app_module):
    today = datetime.now(UTC).strftime("%d.%m.%Y")
    assert app_module._chart_stale_since([[today, 100]]) is None


def test_chart_stale_since_old(app_module):
    old = (datetime.now(UTC) - timedelta(days=10)).strftime("%d.%m.%Y")
    assert app_module._chart_stale_since([[old, 100]]) == old


def test_chart_stale_since_malformed_date(app_module):
    assert app_module._chart_stale_since([["not-a-date", 100]]) is None


def test_db_to_products_and_back(app_module):
    from hotline_prices.config import ProductConfig

    data = {
        "products": [
            {"url": "https://hotline.ua/ua/cat/x/", "count": 2},
            {
                "url": "https://hotline.ua/ua/cat/y/",
                "title": "Y",
                "count": 1,
                "target_price": 500.0,
            },
        ]
    }
    products = app_module._db_to_products(data)
    assert products == [
        ProductConfig(url="https://hotline.ua/ua/cat/x/", count=2),
        ProductConfig(
            url="https://hotline.ua/ua/cat/y/", title="Y", count=1, target_price=500.0
        ),
    ]


def test_products_to_db_drops_none_fields_except_url_and_count(app_module):
    from hotline_prices.config import ProductConfig

    products = [ProductConfig(url="https://hotline.ua/ua/cat/x/", count=3)]
    assert app_module._products_to_db(products) == {
        "products": [{"url": "https://hotline.ua/ua/cat/x/", "count": 3}]
    }


def test_products_to_db_keeps_set_optional_fields(app_module):
    from hotline_prices.config import ProductConfig

    products = [
        ProductConfig(
            url="https://hotline.ua/ua/cat/x/", count=1, target_price=999.0, title="X"
        )
    ]
    result = app_module._products_to_db(products)["products"][0]
    assert result["target_price"] == 999.0
    assert result["title"] == "X"


def test_products_to_db_includes_name_only_when_set(app_module):
    assert "name" not in app_module._products_to_db([])
    assert "name" not in app_module._products_to_db([], name=None)
    assert "name" not in app_module._products_to_db([], name="")
    assert app_module._products_to_db([], name="Laptops")["name"] == "Laptops"
