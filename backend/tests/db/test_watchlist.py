"""Watchlist reads and writes."""

from app.db import DEFAULT_TICKERS, add_watchlist_ticker, get_watchlist, remove_watchlist_ticker


def test_seeded_watchlist_is_the_ten_defaults(db):
    assert get_watchlist() == DEFAULT_TICKERS


def test_add_returns_true_and_appends(db):
    assert add_watchlist_ticker("PYPL") is True
    assert get_watchlist()[-1] == "PYPL"


def test_add_duplicate_returns_false_without_error(db):
    assert add_watchlist_ticker("AAPL") is False
    assert get_watchlist().count("AAPL") == 1


def test_remove_returns_true(db):
    assert remove_watchlist_ticker("AAPL") is True
    assert "AAPL" not in get_watchlist()


def test_remove_absent_returns_false(db):
    assert remove_watchlist_ticker("PYPL") is False


def test_removed_ticker_can_be_added_back(db):
    remove_watchlist_ticker("AAPL")
    assert add_watchlist_ticker("AAPL") is True
    assert get_watchlist()[-1] == "AAPL"


def test_watchlist_is_scoped_by_user(db):
    add_watchlist_ticker("PYPL", user_id="other")
    assert get_watchlist("other") == ["PYPL"]
    assert "PYPL" not in get_watchlist()


def test_ordering_is_oldest_addition_first(db):
    add_watchlist_ticker("PYPL")
    add_watchlist_ticker("SHOP")

    assert get_watchlist() == [*DEFAULT_TICKERS, "PYPL", "SHOP"]
