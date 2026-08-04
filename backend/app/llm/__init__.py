"""LLM chat assistant. See planning/TEAM.md interface 4.

Public API:
    ChatResponse     - Structured reply: message, trades, watchlist_changes
    Trade            - {ticker, side, quantity}
    WatchlistChange  - {ticker, action}
    generate_response - Produce a ChatResponse for a user message; never raises
"""

from .client import generate_response
from .schema import ChatResponse, Trade, WatchlistChange

__all__ = [
    "ChatResponse",
    "Trade",
    "WatchlistChange",
    "generate_response",
]
