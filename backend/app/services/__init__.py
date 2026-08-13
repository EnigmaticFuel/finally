"""Business logic for FinAlly: the seam between HTTP and the database.

Every rule lives behind this seam rather than at the HTTP boundary, so a
non-HTTP caller - Phase 6's LLM path - cannot bypass what a manual request is
held to. Nothing here imports a FastAPI exception type; the taxonomy in
errors.py is the only signalling mechanism.

Public API:
    Conflict           - The request contradicts current state (409)
    NotFound           - The named resource does not exist (404)
    TradeError         - A trade violated a business rule (400)
    TradeResult        - What a filled trade reports back
    execute_trade      - Execute one market order, the published seam
    validate_quantity  - The one share-quantity rule, shared by every caller
    value_portfolio    - Pure per-position figures and portfolio total
"""

from .errors import Conflict, NotFound, TradeError
from .portfolio import value_portfolio
from .trading import TradeResult, execute_trade, validate_quantity

__all__ = [
    "Conflict",
    "NotFound",
    "TradeError",
    "TradeResult",
    "execute_trade",
    "validate_quantity",
    "value_portfolio",
]
