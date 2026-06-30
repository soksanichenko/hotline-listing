"""Data models for price summaries."""

from dataclasses import dataclass, field
from datetime import date


@dataclass
class ProductSummary:
    """Price snapshot for a single product."""

    path: str
    title: str
    hotline_url: str
    price_uah: float
    price_usd: float
    quantity: int
    count: int = 1
    purchase_price: float | None = None
    purchase_date: date | None = None
    price_history_uah: list[float] = field(default_factory=list)
    error: str | None = None

    @property
    def total_uah(self) -> float:
        return self.price_uah * self.count

    @property
    def total_usd(self) -> float:
        return self.price_usd * self.count

    @property
    def price_diff(self) -> float | None:
        """Current price minus purchase price per unit (negative = cheaper now)."""
        if self.purchase_price is None or not self.price_uah:
            return None
        return self.price_uah - self.purchase_price

    @property
    def total_diff(self) -> float | None:
        """price_diff × count."""
        if self.price_diff is None:
            return None
        return self.price_diff * self.count
