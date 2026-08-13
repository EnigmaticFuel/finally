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


class TradeResponse(BaseModel):
    """A filled trade. fill_price is the server's price, not the client's."""

    ticker: str
    side: str
    quantity: float
    fill_price: float
    total_cost: float
    cash_balance: float
    executed_at: str
