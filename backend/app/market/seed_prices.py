"""Seed prices, GBM parameters and correlation groups for the simulator."""

from __future__ import annotations

import hashlib

# Recognisable rather than current. This is a simulation with pretend money.
SEED_PRICES: dict[str, float] = {
    "AAPL": 190.00,
    "GOOGL": 175.00,
    "MSFT": 420.00,
    "AMZN": 185.00,
    "TSLA": 250.00,
    "NVDA": 800.00,
    "META": 500.00,
    "JPM": 195.00,
    "V": 280.00,
    "NFLX": 600.00,
}

# sigma: annualised volatility. mu: annualised drift.
TICKER_PARAMS: dict[str, dict[str, float]] = {
    "AAPL": {"sigma": 0.22, "mu": 0.05},
    "GOOGL": {"sigma": 0.25, "mu": 0.05},
    "MSFT": {"sigma": 0.20, "mu": 0.05},
    "AMZN": {"sigma": 0.28, "mu": 0.05},
    "TSLA": {"sigma": 0.50, "mu": 0.03},  # High volatility
    "NVDA": {"sigma": 0.40, "mu": 0.08},  # High volatility, strong drift
    "META": {"sigma": 0.30, "mu": 0.05},
    "JPM": {"sigma": 0.18, "mu": 0.04},  # Low volatility (bank)
    "V": {"sigma": 0.17, "mu": 0.04},  # Low volatility (payments)
    "NFLX": {"sigma": 0.35, "mu": 0.05},
}

# Correlation groups. TSLA is deliberately in neither: nominally tech, famously
# does its own thing, and its independence gives the watchlist texture.
CORRELATION_GROUPS: dict[str, set[str]] = {
    "tech": {"AAPL", "GOOGL", "MSFT", "AMZN", "META", "NVDA", "NFLX"},
    "finance": {"JPM", "V"},
}

INTRA_TECH_CORR = 0.6  # Tech names move together
INTRA_FINANCE_CORR = 0.5  # Finance names move together
CROSS_GROUP_CORR = 0.3  # Across sectors, TSLA, and synthesised tickers


def synthesize_params(ticker: str) -> tuple[float, dict[str, float]]:
    """Derive a stable seed price and GBM parameters from the symbol itself.

    Deterministic by construction: SHA-256 of the symbol, never random. A user
    holding 10 shares of PYPL bought at $73 must not restart the container and
    find PYPL trading at $412 — their P&L would be nonsense.

    Ranges are chosen so every synthesised ticker looks like an ordinary
    large-cap: $20-$500, sigma 0.15-0.50, mu 0.02-0.08.
    """
    digest = hashlib.sha256(ticker.encode()).digest()
    price = 20.0 + (int.from_bytes(digest[0:4], "big") % 48_000) / 100.0
    sigma = 0.15 + (digest[4] / 255.0) * 0.35
    mu = 0.02 + (digest[5] / 255.0) * 0.06
    return round(price, 2), {"sigma": round(sigma, 4), "mu": round(mu, 4)}


def params_for(ticker: str) -> tuple[float, dict[str, float]]:
    """Seed price and GBM parameters for any well-formed ticker."""
    if ticker in SEED_PRICES:
        return SEED_PRICES[ticker], dict(TICKER_PARAMS[ticker])
    return synthesize_params(ticker)
