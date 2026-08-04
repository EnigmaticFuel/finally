"""Chat endpoints. See PLAN.md sections 8 and 9.

The assistant's actions execute automatically and go through the same services
as the manual endpoints, so trade validation never drifts between the two paths.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.db import add_chat_message, get_chat_messages
from app.llm import ChatResponse, Trade, WatchlistChange, generate_response
from app.services.trading import TradeError, execute_trade
from app.services.watchlist import WatchlistError, add_ticker, remove_ticker

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


@router.get("")
def read_history(limit: int = Query(100, ge=1, le=500)) -> dict:
    """Conversation history, oldest first, so the panel repopulates after a reload."""
    return {"messages": get_chat_messages(limit=limit)}


@router.post("")
async def send_message(request: ChatRequest) -> ChatResponse:
    """Store the user's message, generate a reply, and run whatever it asks for."""
    add_chat_message("user", request.message)

    response = await generate_response(request.message)
    executed = await _execute_actions(response)

    add_chat_message("assistant", executed.message, _actions_json(executed))
    return executed


async def _execute_actions(response: ChatResponse) -> ChatResponse:
    """Run every requested action, returning what actually happened.

    A failed action does not stop the ones after it: its message is folded into
    the reply so the user sees why it failed, and the remaining actions run.
    """
    trades: list[Trade] = []
    watchlist_changes: list[WatchlistChange] = []
    errors: list[str] = []

    for trade in response.trades:
        try:
            await execute_trade(trade.ticker, trade.side, trade.quantity)
        except (TradeError, ValueError) as exc:
            errors.append(str(exc))
        else:
            trades.append(trade)

    for change in response.watchlist_changes:
        try:
            await _apply_change(change)
        except WatchlistError as exc:
            errors.append(str(exc))
        else:
            watchlist_changes.append(change)

    return ChatResponse(
        message="\n".join([response.message, *errors]),
        trades=trades,
        watchlist_changes=watchlist_changes,
    )


async def _apply_change(change: WatchlistChange) -> None:
    if change.action == "add":
        await add_ticker(change.ticker)
    else:
        await remove_ticker(change.ticker)


def _actions_json(response: ChatResponse) -> dict | None:
    """The executed actions to store alongside the message, or None if there were none."""
    if not response.trades and not response.watchlist_changes:
        return None
    return {
        "trades": [trade.model_dump() for trade in response.trades],
        "watchlist_changes": [change.model_dump() for change in response.watchlist_changes],
    }
