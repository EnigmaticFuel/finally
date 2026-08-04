"""Portfolio endpoints. Shapes are fixed by PLAN.md section 8.

Thin over app.services: these handlers translate a TradeError into a 400 and
do nothing else. Every rule lives in the service so the LLM path obeys it too.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.db import get_snapshots
from app.services.portfolio import build_portfolio
from app.services.trading import TradeError, execute_trade

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


class TradeRequest(BaseModel):
    ticker: str
    quantity: float
    side: str


@router.get("")
def read_portfolio() -> dict:
    """Cash, total value and every position priced at the current market."""
    return build_portfolio()


@router.post("/trade")
async def post_trade(request: TradeRequest) -> dict:
    """Execute a market order and return the fill it actually got."""
    try:
        return await execute_trade(request.ticker, request.side, request.quantity)
    except TradeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/history")
def read_history(
    limit: int = Query(500, ge=1, le=5000),
    since: str | None = Query(None, description="ISO 8601 UTC timestamp, exclusive"),
) -> dict:
    """Portfolio value over time for the P&L chart, newest first."""
    return {"snapshots": get_snapshots(limit=limit, since=since)}
