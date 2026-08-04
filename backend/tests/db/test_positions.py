"""Cash balance, positions and the trade audit log."""

import pytest

from app.db import (
    delete_position,
    get_cash_balance,
    get_connection,
    get_position,
    get_positions,
    record_trade,
    set_cash_balance,
    upsert_position,
)


def test_set_and_get_cash_balance(db):
    set_cash_balance(8234.5)
    assert get_cash_balance() == 8234.5


def test_no_positions_on_a_fresh_database(db):
    assert get_positions() == []


def test_upsert_inserts(db):
    upsert_position("AAPL", 10.0, 188.6)
    position = get_position("AAPL")
    assert position["ticker"] == "AAPL"
    assert position["quantity"] == 10.0
    assert position["avg_cost"] == 188.6


def test_upsert_updates_in_place(db):
    upsert_position("AAPL", 10.0, 188.6)
    upsert_position("AAPL", 15.0, 190.0)

    assert get_position("AAPL")["quantity"] == 15.0
    assert len(get_positions()) == 1


def test_upsert_stamps_updated_at(db):
    upsert_position("AAPL", 10.0, 188.6)
    assert get_position("AAPL")["updated_at"].endswith("Z")


def test_get_position_returns_none_when_absent(db):
    assert get_position("AAPL") is None


def test_positions_are_ordered_by_ticker(db):
    for ticker in ("TSLA", "AAPL", "MSFT"):
        upsert_position(ticker, 1.0, 100.0)

    assert [p["ticker"] for p in get_positions()] == ["AAPL", "MSFT", "TSLA"]


def test_position_dict_has_exactly_the_contract_keys(db):
    upsert_position("AAPL", 10.0, 188.6)
    assert set(get_position("AAPL")) == {"ticker", "quantity", "avg_cost", "updated_at"}


def test_fractional_quantities_survive(db):
    upsert_position("AAPL", 0.2534, 188.6)
    assert get_position("AAPL")["quantity"] == pytest.approx(0.2534)


def test_delete_position(db):
    upsert_position("AAPL", 10.0, 188.6)
    delete_position("AAPL")
    assert get_position("AAPL") is None


def test_delete_position_is_a_no_op_when_absent(db):
    delete_position("AAPL")
    assert get_positions() == []


def test_positions_are_scoped_by_user(db):
    upsert_position("AAPL", 10.0, 188.6)
    upsert_position("AAPL", 5.0, 100.0, user_id="other")

    assert get_position("AAPL")["quantity"] == 10.0
    assert get_position("AAPL", user_id="other")["quantity"] == 5.0


def test_record_trade_returns_the_recorded_row(db):
    trade = record_trade("AAPL", "buy", 10.0, 190.52)

    assert set(trade) == {"id", "ticker", "side", "quantity", "price", "executed_at"}
    assert trade["side"] == "buy"
    assert trade["price"] == 190.52
    assert trade["executed_at"].endswith("Z")


def test_record_trade_appends(db):
    record_trade("AAPL", "buy", 10.0, 190.52)
    record_trade("AAPL", "sell", 4.0, 191.0)

    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0] == 2


def test_trade_ids_are_unique(db):
    first = record_trade("AAPL", "buy", 1.0, 190.0)
    second = record_trade("AAPL", "buy", 1.0, 190.0)
    assert first["id"] != second["id"]
