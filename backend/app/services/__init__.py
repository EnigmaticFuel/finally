"""Business logic for FinAlly: the seam between HTTP and the database.

Every rule lives behind this seam rather than at the HTTP boundary, so a
non-HTTP caller - Phase 6's LLM path - cannot bypass what a manual request is
held to. Nothing here imports a FastAPI exception type; the taxonomy in
errors.py is the only signalling mechanism.

Public API:
    Conflict                  - The request contradicts current state (409)
    NotFound                  - The named resource does not exist (404)
    SNAPSHOT_INTERVAL_SECONDS - Seconds between background portfolio snapshots
    TickerQuote               - One watchlist row's live figures, or nulls
    TradeError                - A trade violated a business rule (400)
    TradeResult               - What a filled trade reports back
    WatchlistEntry            - A normalized symbol and whether a row was new
    add                       - Add a ticker to the watchlist and register it with the market source
    execute_trade             - Execute one market order, the published seam
    get_history               - Portfolio value snapshots, newest first
    get_portfolio             - Cash, live-valued positions and the total
    quote                     - One ticker's live figures from the price cache
    read_watchlist            - Every watched ticker with what the cache knows
    record_snapshot           - Record the portfolio total unless it is unchanged
    remove                    - Remove a ticker from the watchlist, refusing while a position is held
    reset_portfolio           - Return cash and positions to the starting state
    snapshot_loop             - The background task recording value every 30 seconds
    validate_quantity         - The one share-quantity rule, shared by every caller
    value_portfolio           - Pure per-position figures and portfolio total

The watchlist seams read better imported module-qualified - `from
app.services.watchlist import add, remove`, or `from app.services import
watchlist` and then `watchlist.add(...)` - because a bare `add` at a call site
says nothing about what is being added. That is also how the ROADMAP names them
for Phase 6.
"""

from .errors import Conflict, NotFound, TradeError
from .portfolio import get_history, get_portfolio, reset_portfolio, value_portfolio
from .snapshots import SNAPSHOT_INTERVAL_SECONDS, record_snapshot, snapshot_loop
from .trading import TradeResult, execute_trade, validate_quantity
from .watchlist import TickerQuote, WatchlistEntry, add, quote, read_watchlist, remove

__all__ = [
    "Conflict",
    "NotFound",
    "SNAPSHOT_INTERVAL_SECONDS",
    "TickerQuote",
    "TradeError",
    "TradeResult",
    "WatchlistEntry",
    "add",
    "execute_trade",
    "get_history",
    "get_portfolio",
    "quote",
    "read_watchlist",
    "record_snapshot",
    "remove",
    "reset_portfolio",
    "snapshot_loop",
    "validate_quantity",
    "value_portfolio",
]
