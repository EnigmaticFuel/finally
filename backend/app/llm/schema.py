"""Structured output schema for the chat assistant. See PLAN.md section 9.

All three fields of ChatResponse are required and none is optional: structured
outputs are more reliable without optional keys, and the parsing code loses its
None branches. A response with nothing to do carries empty lists.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Trade(BaseModel):
    """A trade the assistant wants executed."""

    ticker: str
    side: Literal["buy", "sell"]
    quantity: float


class WatchlistChange(BaseModel):
    """A watchlist modification the assistant wants applied."""

    ticker: str
    action: Literal["add", "remove"]


class ChatResponse(BaseModel):
    """The complete assistant reply: conversational text plus actions to run."""

    message: str
    trades: list[Trade]
    watchlist_changes: list[WatchlistChange]
