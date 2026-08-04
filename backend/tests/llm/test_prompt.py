"""Prompt assembly: live context and conversation history."""

from app.db import add_chat_message, set_cash_balance, upsert_position
from app.llm.prompt import build_messages, portfolio_context


def test_context_reports_cash_positions_and_watchlist(market):
    upsert_position("AAPL", 10, 180.0)
    set_cash_balance(8200.0)

    context = portfolio_context()

    assert "Cash balance: 8200.00" in context
    assert "AAPL: quantity 10, avg cost 180.00, price 190.00" in context
    assert "unrealized P&L 100.00" in context
    assert "GOOGL: price 175.00" in context


def test_context_says_none_when_there_are_no_positions(market):
    assert "Positions: none" in portfolio_context()


def test_messages_start_with_the_system_prompt(market):
    messages = build_messages("hello")
    assert messages[0]["role"] == "system"
    assert "FinAlly, an AI trading assistant" in messages[0]["content"]


def test_messages_end_with_the_new_user_message(market):
    messages = build_messages("hello")
    assert messages[-1] == {"role": "user", "content": "hello"}


def test_history_is_included_oldest_first(market):
    add_chat_message("user", "first")
    add_chat_message("assistant", "second")

    messages = build_messages("third")

    assert messages[-3:] == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "second"},
        {"role": "user", "content": "third"},
    ]


def test_the_just_persisted_user_message_is_not_repeated(market):
    """The endpoint stores the message before generating, so history ends with it."""
    add_chat_message("user", "hello")

    messages = build_messages("hello")

    assert [m for m in messages if m["role"] == "user"] == [{"role": "user", "content": "hello"}]
