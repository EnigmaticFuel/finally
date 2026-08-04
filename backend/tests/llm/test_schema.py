"""The structured output schema: every field required, no optional keys."""

import pytest
from pydantic import ValidationError

from app.llm import ChatResponse, Trade, WatchlistChange


def test_full_response_parses():
    response = ChatResponse.model_validate_json(
        '{"message": "Buying.", "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 10}],'
        ' "watchlist_changes": [{"ticker": "PYPL", "action": "add"}]}'
    )
    assert response.message == "Buying."
    assert response.trades == [Trade(ticker="AAPL", side="buy", quantity=10)]
    assert response.watchlist_changes == [WatchlistChange(ticker="PYPL", action="add")]


def test_empty_lists_are_valid():
    response = ChatResponse.model_validate_json(
        '{"message": "Nothing to do.", "trades": [], "watchlist_changes": []}'
    )
    assert response.trades == []
    assert response.watchlist_changes == []


@pytest.mark.parametrize(
    "payload",
    [
        '{"trades": [], "watchlist_changes": []}',
        '{"message": "hi", "watchlist_changes": []}',
        '{"message": "hi", "trades": []}',
    ],
)
def test_missing_field_is_rejected(payload):
    """No defaults: a missing key must fail rather than be silently filled in."""
    with pytest.raises(ValidationError):
        ChatResponse.model_validate_json(payload)


def test_side_must_be_buy_or_sell():
    with pytest.raises(ValidationError):
        Trade(ticker="AAPL", side="hold", quantity=1)


def test_action_must_be_add_or_remove():
    with pytest.raises(ValidationError):
        WatchlistChange(ticker="AAPL", action="delete")


def test_schema_has_no_optional_fields():
    """Structured outputs are more reliable when every property is required."""
    schema = ChatResponse.model_json_schema()
    assert set(schema["required"]) == {"message", "trades", "watchlist_changes"}
