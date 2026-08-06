-- FinAlly schema. Six tables, transcribed from PLAN.md section 7.
--
-- Every table carries a user_id defaulting to 'default'. The app is single-user
-- today; the column exists so multi-user support needs no migration.
--
-- Every *_at column stores an ISO 8601 UTC string, never epoch seconds. Epoch
-- floats appear in exactly one place in this project: the SSE payload.
--
-- CREATE TABLE IF NOT EXISTS throughout, so applying this script to an existing
-- database is a no-op rather than an error.
--
-- There is deliberately no realized_pnl column. Sale proceeds land in
-- cash_balance and the positions table reports unrealized P&L only; the trades
-- log holds everything needed to derive realized P&L if a panel is ever added.

CREATE TABLE IF NOT EXISTS users_profile (
    id TEXT PRIMARY KEY DEFAULT 'default',
    cash_balance REAL NOT NULL DEFAULT 10000.0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'default',
    ticker TEXT NOT NULL,
    added_at TEXT NOT NULL,
    UNIQUE (user_id, ticker)
);

-- A sell that takes quantity to zero deletes the row: there are no
-- zero-quantity positions.
CREATE TABLE IF NOT EXISTS positions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'default',
    ticker TEXT NOT NULL,
    quantity REAL NOT NULL,
    avg_cost REAL NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (user_id, ticker)
);

-- Append-only audit log. No endpoint reads it and no UI panel shows it.
CREATE TABLE IF NOT EXISTS trades (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'default',
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    executed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'default',
    total_value REAL NOT NULL,
    recorded_at TEXT NOT NULL
);

-- actions holds JSON for assistant messages and is null for user messages.
CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'default',
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    actions TEXT,
    created_at TEXT NOT NULL
);
