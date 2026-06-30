"""Application configuration loaded from YAML."""

from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, model_validator


class ProductConfig(BaseModel):
    """Single product entry from config."""

    url: str
    title: str | None = None
    count: int = 1
    purchase_price: float | None = None
    purchase_date: date | None = None


class AppConfig(BaseModel):
    """Top-level config model."""

    redis_url: str = "redis://localhost:6379"
    database_url: str = "postgresql://postgres:postgres@localhost:5432/hotline_prices"
    cache_ttl: int = 3600
    city_id: int = 154
    products: list[ProductConfig] = []

    @property
    def sync_database_url(self) -> str:
        """SQLAlchemy sync URL for psycopg3 (postgresql+psycopg://...)."""
        return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)

    @property
    def async_database_url(self) -> str:
        """SQLAlchemy async URL for psycopg3 (postgresql+psycopg_async://...)."""
        return self.database_url.replace(
            "postgresql://", "postgresql+psycopg_async://", 1
        )

    @model_validator(mode="before")
    @classmethod
    def _normalize_products(cls, data: dict) -> dict:
        """Accept both string URLs and {url, title} dicts."""
        products = data.get("products", [])
        data["products"] = [{"url": p} if isinstance(p, str) else p for p in products]
        return data

    @classmethod
    def from_yaml(cls, path: Path | str) -> "AppConfig":
        """Load config from a YAML file."""
        with open(path) as f:
            return cls(**yaml.safe_load(f))
