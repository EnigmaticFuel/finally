"""The chat endpoints end to end with LLM_MOCK=true.

The LLM is mocked but nothing else is: every trade and watchlist change here
goes through the real services, so the validation these tests see is the
validation a user gets.
"""

from app.db import get_cash_balance, get_positions, get_watchlist, upsert_position

PATH = "/api/chat"


async def test_history_starts_empty(client):
    response = await client.get(PATH)
    assert response.status_code == 200
    assert response.json() == {"messages": []}


async def test_post_returns_the_full_response_shape(client):
    response = await client.post(PATH, json={"message": "how am I doing"})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"message", "trades", "watchlist_changes"}
    assert body["message"] == "You are holding 0 positions worth $0.00 with $10000.00 in cash."
    assert body["trades"] == []
    assert body["watchlist_changes"] == []


async def test_conversation_is_persisted_oldest_first(client):
    await client.post(PATH, json={"message": "how am I doing"})

    messages = (await client.get(PATH)).json()["messages"]

    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "how am I doing"
    assert messages[0]["actions"] is None
    assert messages[1]["actions"] is None


async def test_history_limit(client):
    await client.post(PATH, json={"message": "first question"})
    await client.post(PATH, json={"message": "second question"})

    messages = (await client.get(PATH, params={"limit": 1})).json()["messages"]

    assert len(messages) == 1
    assert messages[0]["role"] == "assistant"


async def test_buy_executes_through_the_real_trade_path(client):
    response = await client.post(PATH, json={"message": "buy 1 NVDA"})

    body = response.json()
    assert body["trades"] == [{"ticker": "NVDA", "side": "buy", "quantity": 1.0}]

    positions = get_positions()
    assert [p["ticker"] for p in positions] == ["NVDA"]
    assert positions[0]["quantity"] == 1
    assert get_cash_balance() == 10000.0 - 130.0


async def test_executed_actions_are_stored_on_the_assistant_message(client):
    await client.post(PATH, json={"message": "buy 1 NVDA"})

    messages = (await client.get(PATH)).json()["messages"]

    assert messages[1]["actions"] == {
        "trades": [{"ticker": "NVDA", "side": "buy", "quantity": 1.0}],
        "watchlist_changes": [],
    }


async def test_sell_reduces_the_position(client):
    upsert_position("AAPL", 3, 180.0)

    await client.post(PATH, json={"message": "sell AAPL"})

    positions = get_positions()
    assert positions[0]["quantity"] == 2


async def test_failed_trade_is_folded_into_the_message(client):
    response = await client.post(PATH, json={"message": "sell TSLA"})

    body = response.json()
    assert body["trades"] == []
    assert "TSLA" in body["message"]
    assert get_positions() == []


async def test_failed_trade_is_not_recorded_as_an_action(client):
    await client.post(PATH, json={"message": "sell TSLA"})

    messages = (await client.get(PATH)).json()["messages"]
    assert messages[1]["actions"] is None


async def test_watchlist_add_executes(client, market):
    response = await client.post(PATH, json={"message": "add PYPL"})

    assert response.json()["watchlist_changes"] == [{"ticker": "PYPL", "action": "add"}]
    assert "PYPL" in get_watchlist()
    assert market.get_price("PYPL") == 65.0


async def test_watchlist_remove_executes(client, market):
    response = await client.post(PATH, json={"message": "remove META"})

    assert response.json()["watchlist_changes"] == [{"ticker": "META", "action": "remove"}]
    assert "META" not in get_watchlist()
    assert market.get_price("META") is None


async def test_removing_a_held_ticker_is_reported_not_raised(client):
    upsert_position("META", 5, 480.0)

    response = await client.post(PATH, json={"message": "remove META"})

    body = response.json()
    assert response.status_code == 200
    assert body["watchlist_changes"] == []
    assert "META" in body["message"]
    assert "META" in get_watchlist()


async def test_user_message_survives_a_failed_action(client):
    await client.post(PATH, json={"message": "sell TSLA"})

    messages = (await client.get(PATH)).json()["messages"]
    assert messages[0]["content"] == "sell TSLA"


async def test_empty_message_is_rejected(client):
    response = await client.post(PATH, json={"message": ""})
    assert response.status_code == 422
