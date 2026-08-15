"""Request and response models for every Phase 3 route.

These declare shape only - no constraints, no validators. Every business rule
lives in the service layer, called by both the router and Phase 6's LLM path, so
there is one rule, one message and one place the tests point at. A Pydantic
constraint would also return 422 where PLAN.md section 8 requires 400, and Phase
6 never builds a request model at all.

Typed models are what makes Phase 2's decision to keep /docs enabled pay: a
student can read every field and its type before calling anything.

Every *_at field is typed str, holding the ISO 8601 UTC string exactly as
queries.py stored it. Typing them as datetime would make Pydantic re-serialize
and change the string the client sees.
"""

from __future__ import annotations

from pydantic import BaseModel


class TradeRequest(BaseModel):
    """POST /api/portfolio/trade body."""

    ticker: str
    side: str
    quantity: float


class ResetRequest(BaseModel):
    """POST /api/portfolio/reset body, required so the route is not form-forgeable.

    The route is destructive and unauthenticated, and the app sends no CORS
    headers and runs no origin check. Requiring a JSON body forces Content-Type
    application/json, which makes a cross-origin POST a non-simple request: the
    browser must preflight it, and the preflight goes unanswered. A cross-origin
    form, which can only send form-encoded, multipart or text/plain, has no way
    to reach the handler.

    The security property is the requirement of a JSON body, not the value
    carried in it, so confirm gets no default and its value is never read. D-13
    keeps confirmation UX in Phase 4's UI.
    """

    confirm: bool


class TradeResponse(BaseModel):
    """A filled trade. fill_price is the server's price, not the client's."""

    ticker: str
    side: str
    quantity: float
    fill_price: float
    total_cost: float
    cash_balance: float
    executed_at: str


class PositionOut(BaseModel):
    """One held position with its live valuation.

    The four nullable fields are the null rule made explicit in the OpenAPI
    schema: a position whose ticker has no price reports null and is excluded
    from total_value, so the client renders a dash rather than a wrong number.
    """

    ticker: str
    quantity: float
    avg_cost: float
    current_price: float | None
    market_value: float | None
    unrealized_pnl: float | None
    unrealized_pnl_percent: float | None


class PortfolioResponse(BaseModel):
    """GET /api/portfolio and POST /api/portfolio/reset."""

    cash_balance: float
    total_value: float
    positions: list[PositionOut]


class SnapshotOut(BaseModel):
    """One portfolio value point for the P&L chart."""

    total_value: float
    recorded_at: str


class HistoryResponse(BaseModel):
    """GET /api/portfolio/history."""

    snapshots: list[SnapshotOut]


class WatchlistTickerOut(BaseModel):
    """One watched ticker with its live price and sparkline history.

    A ticker with no price yet is present with nulls and an empty history, never
    omitted and never zeroed: the watchlist is database state, not cache state,
    and $0.00 is a real price a client will happily render and multiply.
    """

    ticker: str
    price: float | None
    open_price: float | None
    change_from_open_percent: float | None
    history: list[float]


class WatchlistResponse(BaseModel):
    """GET /api/watchlist."""

    tickers: list[WatchlistTickerOut]


class WatchlistAddRequest(BaseModel):
    """POST /api/watchlist body."""

    ticker: str
