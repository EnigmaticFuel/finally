"""Ticker symbol validation — one rule, shared by every caller."""

from __future__ import annotations

import re

TICKER_PATTERN = re.compile(r"^[A-Z]{1,5}$")


def normalize_ticker(raw: str) -> str:
    """Uppercase, strip, and validate a ticker symbol.

    Raises ValueError if the symbol is not 1-5 A-Z characters. Callers turn
    that into a 400 with the message shown to the user verbatim.

    This validates shape, not existence: the simulator accepts any well-formed
    symbol and synthesizes parameters for it (see seed_prices.py).
    """
    ticker = raw.strip().upper()
    if not TICKER_PATTERN.match(ticker):
        raise ValueError(f"Invalid ticker symbol: {raw!r}")
    return ticker
