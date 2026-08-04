# Team Contract

Six agents build FinAlly in one shared working tree. `planning/PLAN.md` is the
product spec and the final authority. This document is the *engineering* contract:
who owns which files, and the exact Python/HTTP interfaces between them.

**Rule 1 — Never edit a file you do not own.** If you need a change in someone
else's file, report it to the team lead instead.

**Rule 2 — The interfaces below are frozen.** They were agreed before work
started so that everyone could build in parallel. If one is genuinely wrong,
report it; do not unilaterally change it.

**Rule 3 — Your module must pass its own tests before you report done.**

---

## File ownership

| Owner | Files |
|---|---|
| **Team lead** (orchestrator) | `backend/app/main.py`, `backend/app/state.py`, `planning/**`, `CLAUDE.md` |
| **Database Engineer** | `backend/app/db/**`, `backend/tests/db/**` |
| **Backend API Engineer** | `backend/app/api/portfolio.py`, `backend/app/api/watchlist.py`, `backend/app/api/health.py`, `backend/app/services/**`, `backend/tests/api/**`, `backend/tests/services/**` |
| **LLM Engineer** | `backend/app/api/chat.py`, `backend/app/llm/**`, `backend/tests/llm/**` |
| **Frontend Engineer** | `frontend/**` |
| **DevOps Engineer** | `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `scripts/**`, `.env.example`, `.gitignore`, `db/.gitkeep`, `README.md` |
| **Integration Tester** | `test/**` (Playwright E2E, run on the host) |

`backend/app/market/**` is **built, tested and frozen**. Read it, import it, do
not modify it. `backend/pyproject.toml` is shared — only add dependencies, never
restructure; announce any dependency you add.

---

## Backend module layout

```
backend/app/
├── market/       FROZEN — price cache, simulator, Massive client, SSE stream
├── state.py      Process singletons: price cache + market source (lead)
├── db/           Schema, lazy init, all SQL (Database Engineer)
├── services/     Business logic: trading, watchlist, snapshots (Backend API)
├── api/          FastAPI routers (Backend API; chat.py is LLM Engineer)
├── llm/          LiteLLM client, mock, structured-output schema (LLM Engineer)
└── main.py       App assembly, lifespan, router registration, static mount (lead)
```

---

## Interface 1 — `app.state`

Owned by the lead, already written. Everyone reads prices through this.

```python
from app.state import get_cache, get_source

cache = get_cache()      # PriceCache — see backend/CLAUDE.md
source = get_source()    # MarketDataSource — add_ticker / remove_ticker
```

Both raise `RuntimeError` if called before startup. Tests use
`app.state.set_market(cache, source)` to install fakes.

---

## Interface 2 — `app.db` (Database Engineer provides, everyone consumes)

Synchronous `sqlite3`. All functions take a trailing `user_id: str = DEFAULT_USER_ID`.
Every `*_at` value returned is an **ISO 8601 UTC string** (`2026-08-04T14:03:11Z`).
Money and quantities are floats.

```python
from app.db import (
    DEFAULT_USER_ID, init_db,
    get_cash_balance, set_cash_balance,
    get_positions, get_position, upsert_position, delete_position,
    get_watchlist, add_watchlist_ticker, remove_watchlist_ticker,
    record_trade,
    record_snapshot, get_snapshots, get_latest_snapshot_value,
    get_chat_messages, add_chat_message,
)
```

| Function | Returns |
|---|---|
| `init_db()` | `None`. Creates the file, schema and seed data if absent. Idempotent, safe to call on every startup. |
| `get_cash_balance()` | `float` |
| `set_cash_balance(balance: float)` | `None` |
| `get_positions()` | `list[dict]` — `{"ticker", "quantity", "avg_cost", "updated_at"}`, ordered by ticker |
| `get_position(ticker)` | same dict or `None` |
| `upsert_position(ticker, quantity, avg_cost)` | `None` — insert or update, sets `updated_at` |
| `delete_position(ticker)` | `None` — used when a sell takes quantity to zero |
| `get_watchlist()` | `list[str]` — tickers, ordered by `added_at` ascending |
| `add_watchlist_ticker(ticker)` | `bool` — `False` if already present (no error) |
| `remove_watchlist_ticker(ticker)` | `bool` — `False` if not present |
| `record_trade(ticker, side, quantity, price)` | `dict` — `{"id","ticker","side","quantity","price","executed_at"}` |
| `record_snapshot(total_value)` | `dict` — `{"total_value","recorded_at"}` |
| `get_snapshots(limit=500, since=None)` | `list[dict]` — `{"total_value","recorded_at"}`, **newest first**; `since` is an ISO string |
| `get_latest_snapshot_value()` | `float | None` — lets the snapshot task skip unchanged writes |
| `get_chat_messages(limit=100)` | `list[dict]` — `{"role","content","actions","created_at"}`, **oldest first**; `actions` is already JSON-decoded (`dict | None`) |
| `add_chat_message(role, content, actions=None)` | `dict` — same shape; `actions` is JSON-encoded on write |

**Database location.** `init_db()` resolves the path from the `FINALLY_DB_PATH`
environment variable, defaulting to `<repo root>/db/finally.db`. Tests set that
variable to a tmp path. Nothing else in the codebase opens the file.

---

## Interface 3 — `app.services` (Backend API Engineer provides, LLM Engineer consumes)

The single execution path for a trade. The manual endpoint and the LLM both call
it, so validation cannot drift between them.

```python
from app.services.trading import execute_trade, TradeError
from app.services.watchlist import add_ticker, remove_ticker, WatchlistError
from app.services.portfolio import build_portfolio
from app.services.snapshots import record_now
```

```python
class TradeError(Exception):
    """message is shown to the user verbatim (PLAN.md section 8)."""

async def execute_trade(ticker: str, side: str, quantity: float) -> dict:
    """Validate, fill at the server price, persist, snapshot.

    Returns {"ticker","side","quantity","fill_price","total_cost",
             "cash_balance","executed_at"}.
    Raises TradeError on any rule violation. Adds the ticker to the
    watchlist and the market source if it is not already tracked.
    """

class WatchlistError(Exception):
    status_code: int   # 400 invalid symbol, 404 unknown on delete, 409 position held

async def add_ticker(ticker: str) -> None
async def remove_ticker(ticker: str) -> None

def build_portfolio() -> dict:
    """{"cash_balance", "total_value", "positions": [...]} per PLAN.md section 8."""

def record_now() -> None:
    """Write a portfolio_snapshots row now, skipping an unchanged value."""

@asynccontextmanager
async def snapshot_task():
    """Run the 30-second snapshot loop for the lifetime of the app.
    main.py already wraps the application in this; keep the signature."""
```

`build_portfolio()` prices positions from `get_cache()`. A position whose ticker
has no cached price yet is valued at its `avg_cost` rather than dropped.

---

## Interface 4 — `app.llm` (LLM Engineer provides)

```python
from app.llm import ChatResponse, generate_response

class ChatResponse(BaseModel):
    message: str
    trades: list[Trade]                    # {ticker, side, quantity}
    watchlist_changes: list[WatchlistChange]  # {ticker, action}

async def generate_response(user_message: str) -> ChatResponse:
    """Real LiteLLM call, mock when LLM_MOCK=true, friendly degraded
    response when OPENROUTER_API_KEY is missing. Never raises."""
```

Action execution lives in `app/api/chat.py`, which calls `execute_trade` and the
watchlist services and folds any `TradeError` message into the chat reply.

---

## Interface 5 — HTTP (Frontend Engineer consumes)

Exactly the endpoints and JSON shapes in **PLAN.md section 8**. That section is
the contract; nothing here overrides it. Summary:

```
GET    /api/health
GET    /api/stream/prices          SSE — one event, all tickers, keyed by symbol
GET    /api/portfolio
POST   /api/portfolio/trade        {ticker, quantity, side}
GET    /api/portfolio/history      ?limit= &since=
GET    /api/watchlist
POST   /api/watchlist              {ticker}
DELETE /api/watchlist/{ticker}
GET    /api/chat                   ?limit=
POST   /api/chat                   {message}
```

Errors are `{"detail": "..."}` with 400 / 404 / 409. Messages are written to be
displayed to the user verbatim.

The frontend is a Next.js static export served by FastAPI at the same origin, so
every call is a same-origin relative path. No CORS, no API base URL, no env var.

---

## Conventions

- **Timestamps.** SSE payloads carry Unix epoch seconds (float). Every REST
  response and every `*_at` column is an ISO 8601 UTC string. They never mix.
- **Ticker validation.** One rule, shared: `from app.market import normalize_ticker`.
  Uppercase, strip, `^[A-Z]{1,5}$`, `ValueError` otherwise. Never write your own.
- **Fill price.** Always the server-side cache price at the moment the request
  lands, obtained via `from app.market import wait_for_price` (2s grace for a
  just-added ticker). Never trust a price sent by the client.
- **Style.** Follow the root `CLAUDE.md`: simple, incremental, no defensive
  programming, no emojis anywhere in code or output, clear docstrings, sparse
  inline comments, short functions.
- **Python.** `uv` only — `uv add x`, `uv run pytest`. Never `pip`, never `python`.
- **Lint.** `uv run --extra dev ruff check app/ tests/` must pass clean.

---

## Build order and status

Tracked by the lead. Steps 2 and 3 unblock 4; everything else is parallel.

| # | Item | Owner |
|---|---|---|
| 1 | Market data + session baseline | **done, frozen** |
| 2 | Database, schema, lazy init, seed | Database Engineer |
| 3 | Portfolio + watchlist + health APIs, snapshot task | Backend API Engineer |
| 4 | Frontend shell, SSE wiring, watchlist, header, trade bar | Frontend Engineer |
| 5 | Charts — main chart, sparklines, heatmap, P&L | Frontend Engineer |
| 6 | Chat API, mock mode, LiteLLM integration | LLM Engineer |
| 7 | Dockerfile, start/stop scripts, env example | DevOps Engineer |
| 8 | Playwright E2E | Integration Tester |
