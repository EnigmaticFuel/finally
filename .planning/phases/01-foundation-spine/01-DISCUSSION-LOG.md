# Phase 1: Foundation & Spine - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-05
**Phase:** 1-Foundation & Spine
**Areas discussed:** Async DB strategy, Connection & transaction model, Schema & lazy init, Runtime boundaries, Money & quantity rounding, Test strategy

---

## Area selection

| Option | Description | Selected |
|--------|-------------|----------|
| Async DB strategy | aiosqlite vs stdlib sqlite3 + asyncio.to_thread (CORE-10) | ✓ |
| Connection & txn model | Shared connection, per-request, or pool (CORE-05) | ✓ |
| Schema & lazy init | schema.sql vs Python DDL; what triggers lazy init (CORE-04) | ✓ |
| Runtime boundaries | What `/` serves pre-frontend; DB path local vs container (CORE-09) | ✓ |

**User's choice:** All four.
**Notes:** An earlier presentation of the same four options was cancelled accidentally and re-asked verbatim.

---

## Async DB strategy

### How should SQLite be kept off the event loop?

| Option | Description | Selected |
|--------|-------------|----------|
| sqlite3 + to_thread | Stdlib sqlite3 offloaded with asyncio.to_thread; no new dependency; matches massive_client.py | ✓ |
| aiosqlite | Async-native API; new dependency; still runs a thread per connection internally | |
| sqlite3 inline, no offload | Simplest; a slow write stalls every SSE client; violates CORE-10 | |

**User's choice:** sqlite3 + to_thread (recommended).

### Where does the thread offload live?

| Option | Description | Selected |
|--------|-------------|----------|
| Sync queries, callers wrap | Plain `def` query functions; one helper does the to_thread; testable without an event loop | ✓ |
| Every query is async | Uniform await surface; offload duplicated across ~15 functions; every DB test needs a loop | |
| Repository class, async methods | Injectable seam for Phase 3; a layer PLAN.md does not ask for | |

**User's choice:** Sync queries, callers wrap (recommended).
**Notes:** Flagged during the question as the signature contract Phase 3's services inherit.

---

## Connection & transaction model

### Connection lifecycle

| Option | Description | Selected |
|--------|-------------|----------|
| One per operation | Context manager sets WAL + busy_timeout on open; sidesteps check_same_thread | ✓ |
| One shared connection + lock | Cheapest per call; serializes reads behind writes, discarding WAL's benefit | |
| Thread-local connections | Fastest steady-state; murkier WAL checkpointing and test teardown | |

**User's choice:** One per operation (recommended).

### busy_timeout value

| Option | Description | Selected |
|--------|-------------|----------|
| 5000ms | Absorbs snapshot/trade contention; a real lock problem still surfaces visibly | ✓ |
| 30000ms | Maximum resilience on a flaky bind mount; makes contention invisible | |
| 1000ms | Surfaces contention immediately; likely spurious errors in normal overlap | |

**User's choice:** 5000ms (recommended).
**Notes:** Framed against the accepted OneDrive / Windows bind-mount risk — the roadmap says diagnose `database is locked`, not work around it.

### BEGIN IMMEDIATE scope

| Option | Description | Selected |
|--------|-------------|----------|
| Writes only | `writing()` context manager; reads use autocommit, consistent under WAL | ✓ |
| All access, reads included | One uniform entry point; ceremony on every read | |

**User's choice:** Writes only (recommended).

### How routers get a connection

| Option | Description | Selected |
|--------|-------------|----------|
| FastAPI dependency | Overridable in tests; the seam Phase 3's routers reuse | ✓ |
| Path on app.state, queries open their own | Fewer moving parts; tests must reach into app.state | |
| Module-level connection helper | Simplest to call; the singleton pattern CORE-07 rejects | |

**User's choice:** FastAPI dependency (recommended).

---

## Schema & lazy init

### Schema definition form

| Option | Description | Selected |
|--------|-------------|----------|
| schema.sql + executescript | Matches PLAN.md §4's "schema SQL definitions"; readable, diffable; hatchling packages it | ✓ |
| Python DDL constants | No packaging question; loses SQL highlighting | |
| One .sql per table | Cleanest per-table diffs; adds ordering logic for no gain at six tables | |

**User's choice:** schema.sql + executescript (recommended).

### Init trigger

| Option | Description | Selected |
|--------|-------------|----------|
| Connection helper, once-guarded | Covers request handlers and the Phase 3 snapshot task alike; impossible to forget | ✓ |
| FastAPI dependency only | Explicit; the background task bypasses dependencies and can drift | |
| Lifespan startup | Simplest; eager rather than lazy, reads against CORE-04 | |

**User's choice:** Connection helper, once-guarded (recommended).

### Seed gate

| Option | Description | Selected |
|--------|-------------|----------|
| Fresh-DB gate on users_profile | Seed once on an empty database; an emptied watchlist stays empty across restarts | ✓ |
| Per-table emptiness checks | Self-healing; silently refills a deliberately emptied watchlist | |
| INSERT OR IGNORE everywhere | Fully idempotent for the watchlist; does not generalize to UUID-keyed tables | |

**User's choice:** Fresh-DB gate (recommended).

### Source of the ten default tickers

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit in the db seed module | Separates user data from simulator tuning; keeps market/ a pure consumer relationship | ✓ |
| Derive from market.seed_prices.SEED_PRICES | Single source of truth; a simulator-tuning edit would silently change the default watchlist | |

**User's choice:** Explicit in the db seed module (recommended).

---

## Runtime boundaries

### What `/` serves in Phase 1

| Option | Description | Selected |
|--------|-------------|----------|
| Committed placeholder index.html | Mount is real from day one; shadowing test has a target; Phase 7 overwrites the directory | ✓ |
| Create the directory at runtime if absent | The defensive branch the style rules push against | |
| Defer the mount to Phase 2 | Drops CORE-09 and success criterion 1 from this phase — a roadmap change | |

**User's choice:** Committed placeholder (recommended).

### DB path resolution

| Option | Description | Selected |
|--------|-------------|----------|
| FINALLY_DB_PATH env var with a default | Zero-setup local dev; one knob for Phase 2's Dockerfile and scripts | ✓ |
| Pure derivation, no env var | One less variable; dev writes to backend/db while the container uses /app/db | |
| Env var, required, no default | Unambiguous; every `uv run` and pytest invocation needs it set | |

**User's choice:** Env var with a default (recommended).

### Config reading

| Option | Description | Selected |
|--------|-------------|----------|
| app/config.py, plain os.getenv | Matches factory.py's existing style; no dependency beyond dotenv | ✓ |
| pydantic-settings BaseSettings | Typed and validated; another dependency for four strings | |
| os.getenv at each use site | Zero indirection; nothing owns the .env load | |

**User's choice:** app/config.py, plain os.getenv (recommended).

### Where /api/health lives

| Option | Description | Selected |
|--------|-------------|----------|
| app/api/health.py, router factory | Mirrors create_stream_router; establishes the package Phase 3 extends | ✓ |
| Inline in main.py | Fewest files; Phase 3 then has to create app/api/ and move it | |

**User's choice:** app/api/health.py, router factory (recommended).

---

## Money & quantity rounding

### Stored precision

| Option | Description | Selected |
|--------|-------------|----------|
| cash 2dp, qty 4dp, avg_cost 4dp | avg_cost is a derived ratio; 2dp accumulates P&L drift across partial buys | ✓ |
| cash 2dp, qty 4dp, avg_cost 2dp | Uniform money rule; accepts the drift | |
| cash 2dp, qty 4dp, avg_cost 6dp | Negligible drift; stores more precision than any display shows | |

**User's choice:** cash 2dp, qty 4dp, avg_cost 4dp (recommended).
**Notes:** Recorded in CONTEXT.md as the phase's one genuinely one-way decision — `db/finally.db` is tracked in git, so old values survive into every clone.

### Epsilon

| Option | Description | Selected |
|--------|-------------|----------|
| 1e-6 | Two orders below 4dp precision, far above float noise | ✓ |
| 1e-9 | Tighter than the stored precision; catches nothing the round did not | |
| 5e-5 | Derived from 4dp; large enough to swallow a genuine 0.0001-share position | |

**User's choice:** 1e-6 (recommended).

### Where the rules live

| Option | Description | Selected |
|--------|-------------|----------|
| app/db/money.py helper module | Phase 3's manual path and Phase 6's LLM path share one implementation | ✓ |
| Inline in each write function | No indirection; the rule gets restated in every writer | |

**User's choice:** app/db/money.py (recommended).

### Read-path rounding

| Option | Description | Selected |
|--------|-------------|----------|
| No — write boundary only | Matches CORE-06; the client recomputes these live from SSE anyway | ✓ |
| Yes — round derived money to 2dp | Tidier raw JSON; would visibly disagree with the client's own computation | |

**User's choice:** No — write boundary only (recommended).

---

## Test strategy

### Test database backing

| Option | Description | Selected |
|--------|-------------|----------|
| tmp-file via tmp_path | The only option that can exercise WAL, busy_timeout and real contention | ✓ |
| :memory: mostly, tmp-file for locking | Faster; two setups to maintain, and per-operation connections each get an empty DB | |

**User's choice:** tmp-file via tmp_path (recommended).

### Concurrency test for success criterion 3

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — threads hammering both writers | Proves the stated criterion; nothing currently drives this code concurrently | ✓ |
| No — defer to Phase 3 | More realistic once the real task exists; leaves the criterion unproven at verification | |

**User's choice:** Yes (recommended).

### httpx SSE integration test

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — the blocker was the missing app | Closes the ~31% coverage gap CONCERNS.md attributes to having no main.py; covers CORE-03 | ✓ |
| No — leave to Phase 7 E2E | Avoids duplicate coverage; a broken stream surfaces only at the last phase | |

**User's choice:** Yes (recommended).

### Test fixture shape

| Option | Description | Selected |
|--------|-------------|----------|
| Override the FastAPI dependency | Consistent with the chosen seam; Phase 3 reuses it verbatim | ✓ |
| monkeypatch FINALLY_DB_PATH | Exercises real resolution; fragile against import-time ordering in config.py | |

**User's choice:** Override the FastAPI dependency (recommended).

---

## Claude's Discretion

The user selected the recommended option in every question, so nothing was explicitly delegated. Left open by omission: internal module decomposition beyond the file names fixed above, docstring and log-message wording, and the mechanics of the SETUP-03 `.gitattributes` renormalization.

## Deferred Ideas

- 30-second portfolio snapshot background task — Phase 3
- Reset Portfolio (PORT-14) — Phase 3; shape the seed helper so it can be reused
- Realistic snapshot-task-versus-`execute_trade` collision test — Phase 3
- Relaxing the exact `massive==2.2.0` pin — tech debt, frozen module
- `PriceCache.version` read outside the lock — tech debt, frozen module

## Findings surfaced during discussion

- `httpx` is not a dev dependency; the SSE integration test requires adding it. SETUP-01 does not mention it.
- `app.market` already exports `wait_for_price`, prebuilding Phase 3's 2-second price wait.
- `app.frontend()` (FastAPI >=0.141.1) postdates reliable model knowledge; its signature must be read from the installed package during research.

No scope creep was raised — the discussion stayed inside the phase boundary throughout.
