"""Chat history storage and JSON action encoding."""

from app.db import add_chat_message, get_chat_messages, get_connection

ACTIONS = {"trades": [{"ticker": "AAPL", "side": "buy", "quantity": 1}], "watchlist_changes": []}


def test_history_is_empty_on_a_fresh_database(db):
    assert get_chat_messages() == []


def test_add_returns_the_stored_message(db):
    message = add_chat_message("user", "How is my portfolio?")
    assert set(message) == {"role", "content", "actions", "created_at"}
    assert message["role"] == "user"
    assert message["actions"] is None
    assert message["created_at"].endswith("Z")


def test_messages_come_back_oldest_first(db):
    add_chat_message("user", "first")
    add_chat_message("assistant", "second")
    add_chat_message("user", "third")

    assert [m["content"] for m in get_chat_messages()] == ["first", "second", "third"]


def test_limit_keeps_the_most_recent_still_oldest_first(db):
    for content in ("first", "second", "third"):
        add_chat_message("user", content)

    assert [m["content"] for m in get_chat_messages(limit=2)] == ["second", "third"]


def test_actions_round_trip_as_a_dict(db):
    add_chat_message("assistant", "Bought 1 AAPL.", ACTIONS)
    assert get_chat_messages()[0]["actions"] == ACTIONS


def test_actions_are_stored_as_json_text(db):
    add_chat_message("assistant", "Bought 1 AAPL.", ACTIONS)
    with get_connection() as conn:
        stored = conn.execute("SELECT actions FROM chat_messages").fetchone()[0]
    assert isinstance(stored, str)
    assert "AAPL" in stored


def test_user_messages_store_null_actions(db):
    add_chat_message("user", "buy 1 AAPL")
    with get_connection() as conn:
        assert conn.execute("SELECT actions FROM chat_messages").fetchone()[0] is None


def test_messages_are_scoped_by_user(db):
    add_chat_message("user", "mine")
    add_chat_message("user", "theirs", user_id="other")

    assert [m["content"] for m in get_chat_messages()] == ["mine"]
    assert [m["content"] for m in get_chat_messages(user_id="other")] == ["theirs"]
