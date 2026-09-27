from hotline_prices.models import ProductSummary


def _summary(**overrides) -> ProductSummary:
    base = {
        "path": "a",
        "title": "A",
        "hotline_url": "https://hotline.ua/ua/cat/a/",
        "price_uah": 1000,
        "price_usd": 25,
        "quantity": 3,
    }
    base.update(overrides)
    return ProductSummary(**base)


def test_totals_multiply_by_count():
    summary = _summary(price_uah=1000, price_usd=25, count=3)
    assert summary.total_uah == 3000
    assert summary.total_usd == 75


def test_price_diff_none_without_purchase_price():
    summary = _summary(purchase_price=None)
    assert summary.price_diff is None
    assert summary.total_diff is None


def test_price_diff_none_when_price_uah_is_zero():
    summary = _summary(price_uah=0, purchase_price=900)
    assert summary.price_diff is None
    assert summary.total_diff is None


def test_price_diff_negative_when_cheaper_now():
    summary = _summary(price_uah=800, purchase_price=1000, count=2)
    assert summary.price_diff == -200
    assert summary.total_diff == -400


def test_price_diff_positive_when_pricier_now():
    summary = _summary(price_uah=1200, purchase_price=1000)
    assert summary.price_diff == 200
    assert summary.total_diff == 200
