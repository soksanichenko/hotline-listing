from datetime import date

import pytest

from hotline_prices.config import AppConfig, ProductConfig


def test_app_config_defaults():
    cfg = AppConfig()
    assert cfg.redis_url == "redis://localhost:6379"
    assert (
        cfg.database_url
        == "postgresql://postgres:postgres@localhost:5432/hotline_prices"
    )
    assert cfg.cache_ttl == 3600
    assert cfg.city_id == 154
    assert cfg.products == []
    assert cfg.price_check_interval == 1800
    assert cfg.smtp_host == "mail.zelgray.work"
    assert cfg.smtp_port == 587
    assert cfg.smtp_username == ""
    assert cfg.smtp_password == ""
    assert cfg.smtp_from == "noreply@zelgray.work"


def test_sync_database_url_swaps_driver():
    cfg = AppConfig(database_url="postgresql://u:p@host:5432/db")
    assert cfg.sync_database_url == "postgresql+psycopg://u:p@host:5432/db"


def test_async_database_url_swaps_driver():
    cfg = AppConfig(database_url="postgresql://u:p@host:5432/db")
    assert cfg.async_database_url == "postgresql+psycopg_async://u:p@host:5432/db"


def test_normalize_products_accepts_strings_and_dicts():
    cfg = AppConfig(
        products=[
            "https://hotline.ua/ua/cat/a/",
            {"url": "https://hotline.ua/ua/cat/b/", "title": "B", "count": 2},
        ]
    )
    assert len(cfg.products) == 2
    assert cfg.products[0] == ProductConfig(url="https://hotline.ua/ua/cat/a/")
    assert cfg.products[1].title == "B"
    assert cfg.products[1].count == 2


def test_from_yaml_overrides_and_keeps_defaults(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("cache_ttl: 60\nproducts:\n  - https://hotline.ua/ua/cat/a/\n")
    cfg = AppConfig.from_yaml(path)
    assert cfg.cache_ttl == 60
    assert cfg.products == [ProductConfig(url="https://hotline.ua/ua/cat/a/")]
    assert cfg.city_id == 154
    assert cfg.redis_url == "redis://localhost:6379"


def test_from_yaml_accepts_str_path(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("city_id: 1\n")
    cfg = AppConfig.from_yaml(str(path))
    assert cfg.city_id == 1


@pytest.mark.parametrize("value", [None, 100.5])
def test_product_config_optional_prices(value):
    product = ProductConfig(
        url="https://hotline.ua/ua/cat/a/", target_price=value, purchase_price=value
    )
    assert product.target_price == value
    assert product.purchase_price == value


def test_product_config_parses_iso_purchase_date():
    product = ProductConfig(
        url="https://hotline.ua/ua/cat/a/", purchase_date="2026-01-15"
    )
    assert product.purchase_date == date(2026, 1, 15)
