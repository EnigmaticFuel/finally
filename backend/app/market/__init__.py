"""Market data subsystem for FinAlly.

Public API:
    PriceUpdate         - Immutable price snapshot dataclass
    PriceCache          - Thread-safe in-memory price store
    wait_for_price       - Poll the cache for a first tick on a new ticker
    MarketDataSource    - Abstract interface for data providers
    create_market_data_source - Factory that selects simulator or Massive
    create_stream_router - FastAPI router factory for SSE endpoint
    TICKER_PATTERN       - Shared ticker validation regex
    normalize_ticker      - Uppercase, strip, and validate a ticker symbol
"""

from .cache import PriceCache, wait_for_price
from .factory import create_market_data_source
from .interface import MarketDataSource
from .models import PriceUpdate
from .stream import create_stream_router
from .tickers import TICKER_PATTERN, normalize_ticker

__all__ = [
    "MarketDataSource",
    "PriceCache",
    "PriceUpdate",
    "TICKER_PATTERN",
    "create_market_data_source",
    "create_stream_router",
    "normalize_ticker",
    "wait_for_price",
]
