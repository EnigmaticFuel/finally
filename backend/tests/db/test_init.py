"""Schema creation, seed data and idempotency."""

from app.db import (
    DEFAULT_TICKERS,
    get_cash_balance,
    get_connection,
    get_snapshots,
    get_watchlist,
    init_db,
    set_cash_balance,
)

EXPECTED_TABLES = {
    "users_profile",
    "watchlist",
    "positions",
    "trades",
    "portfolio_snapshots",
    "chat_messages",
}


def _names(kind: str) -> set[str]:
    with get_connection() as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = ?", (kind,)).fetchall()
    return {row["name"] for row in rows}


def test_creates_the_database_file(db_path):
    assert not db_path.exists()
    init_db()
    assert db_path.exists()


def test_creates_all_six_tables(db):
    assert EXPECTED_TABLES <= _names("table")


def test_creates_the_read_pattern_indexes(db):
    assert {"idx_snapshots_user_time", "idx_chat_user_time"} <= _names("index")


def test_seeds_one_profile_with_ten_thousand_cash(db):
    assert get_cash_balance() == 10000.0


def test_seeds_the_ten_default_tickers_in_order(db):
    assert get_watchlist() == DEFAULT_TICKERS


def test_seeds_one_opening_snapshot(db):
    snapshots = get_snapshots()
    assert len(snapshots) == 1
    assert snapshots[0]["total_value"] == 10000.0


def test_starts_with_no_positions_trades_or_messages(db):
    with get_connection() as conn:
        for table in ("positions", "trades", "chat_messages"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_is_idempotent(db):
    init_db()
    init_db()

    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users_profile").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0] == 10
        assert conn.execute("SELECT COUNT(*) FROM portfolio_snapshots").fetchone()[0] == 1


def test_does_not_reset_existing_state(db):
    set_cash_balance(500.0)
    init_db()
    assert get_cash_balance() == 500.0


def test_unique_constraints_hold(db):
    with get_connection() as conn:
        rows = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table'").fetchall()
    schema = " ".join(row["sql"] for row in rows)
    assert schema.count("UNIQUE (user_id, ticker)") == 2
