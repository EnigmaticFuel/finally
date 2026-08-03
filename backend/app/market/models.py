"""Data models for market data."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PriceUpdate:
    """Immutable snapshot of a single ticker's price at a point in time.

    Constructed only by PriceCache.update(), which supplies previous_price and
    open_price from the entry it is replacing. Sources never build one directly.
    """

    ticker: str
    price: float
    previous_price: float
    open_price: float
    timestamp: float = field(default_factory=time.time)  # Unix epoch seconds

    # --- Derived: tick over tick ---

    @property
    def change(self) -> float:
        """Absolute price change since the previous tick."""
        return round(self.price - self.previous_price, 4)

    @property
    def change_percent(self) -> float:
        """Percent change since the previous tick. Drives the flash animation only."""
        if self.previous_price == 0:
            return 0.0
        return round((self.price - self.previous_price) / self.previous_price * 100, 4)

    @property
    def direction(self) -> str:
        """'up', 'down' or 'flat' since the previous tick."""
        if self.price > self.previous_price:
            return "up"
        if self.price < self.previous_price:
            return "down"
        return "flat"

    # --- Derived: against the session baseline ---

    @property
    def change_from_open(self) -> float:
        """Absolute price change since the session open."""
        return round(self.price - self.open_price, 4)

    @property
    def change_from_open_percent(self) -> float:
        """Percent change since the session open. This is the user-facing 'change %'."""
        if self.open_price == 0:
            return 0.0
        return round((self.price - self.open_price) / self.open_price * 100, 4)

    def to_dict(self) -> dict:
        """Serialize for JSON / SSE. Keys match the payload in PLAN.md section 6."""
        return {
            "ticker": self.ticker,
            "price": self.price,
            "previous_price": self.previous_price,
            "open_price": self.open_price,
            "timestamp": self.timestamp,
            "change": self.change,
            "change_percent": self.change_percent,
            "change_from_open_percent": self.change_from_open_percent,
            "direction": self.direction,
        }
