---
phase: 01-foundation-spine
plan: 03
subsystem: persistence
tags: [sqlite, queries, parameter-binding, concurrency, wal, begin-immediate, audit-log]
status: complete

requires:
  - "connect, writing, run_db and the plain-def convention from plan 01-02"
  - "apply_schema, seed_fresh, DEFAULT_TICKERS, DEFAULT_USER_ID, STARTING_CASH from plan 01-02"
  - "round_money and round_quantity from plan 01-02"
  - "normalize_ticker from the frozen app/market/tickers.py"
  - "create_app() and the app fixture from plan 01-01"
provides:
  - "The complete query surface in backend/app/db/queries.py: 16 functions across profile, positions, trades, snapshots, watchlist and chat"
  - "add_watchlist_ticker, which Phase 3's execute_trade needs for its auto-add rule"
  - "insert_trade returning the stored executed_at, so the trade response reports the timestamp actually written"
  - "backend/tests/db/test_concurrency.py — the zero-lost-updates proof for Phase 1 success criterion 3"
  - "main.py starting the market source from app.db.seed.DEFAULT_TICKERS"
affects:
  - "phase 3 portfolio service (get_profile, update_cash_balance, get_positions, upsert_position, delete_position, insert_trade, insert_snapshot)"
  - "phase 3 watchlist service (get_watchlist, add_watchlist_ticker, remove_watchlist_ticker, is_ticker_watched; the 409 held-position rule composes get_position with remove_watchlist_ticker)"
  - "phase 3 snapshot background task (get_latest_snapshot to skip an unchanged write)"
  - "phase 6 chat (insert_chat_message, get_chat_messages, and the same trade path)"

tech-stack:
  added: []
  patterns:
    - "One query module; plain def, sqlite3.Connection first, user_id last with a default"
    - "Question-mark placeholders on every value, including limits and the since filter"
    - "Ticker arguments through the single shared normalize_ticker rule, never a second regex"
    - "Upsert and ignore-on-conflict driven by UNIQUE (user_id, ticker) rather than read-then-branch"
    - "rowid as an explicit ordering tiebreaker, because the Windows clock ties ISO timestamps"
    - "Threads plus a collected-exception list for concurrency proofs; real tmp_path file databases only"

key-files:
  created:
    - backend/app/db/queries.py
    - backend/tests/db/test_queries.py
    - backend/tests/db/test_concurrency.py
  modified:
    - backend/app/db/__init__.py
    - backend/app/main.py
    - backend/tests/test_main.py

decisions:
  - "insert_trade returns the stored executed_at rather than None, so Phase 3's trade response cannot report a second, differently-generated timestamp"
  - "Every ORDER BY on a timestamp carries a rowid tiebreaker: Python 3.12 on Windows resolves time.time() to ~15ms, so consecutive inserts genuinely share a recorded_at"
  - "get_snapshots uses one statement with (? IS NULL OR recorded_at >= ?) rather than branching into a second SQL string"
  - "get_chat_messages applies its limit newest-first in a subquery and flips back to oldest-first, so the limit keeps the newest while the result reads forward"
  - "The held-position rule is deliberately absent from queries.py; it is a business rule for Phase 3's service seam where the 409 is raised"
  - "delete_position returns None while remove_watchlist_ticker returns bool: only the watchlist path needs the answer, for its 404"
  - "_utc_now is a private one-liner in queries.py mirroring seed.py's rather than promoting seed.py's to public, to keep this plan's diff inside its own files"

metrics:
  duration: "~45m"
  completed: 2026-08-06
  tasks: 3
  commits: 4
  files_created: 3
  files_modified: 3
  tests_added: 40

actuals:
  tokens: 9000
  tasks: 3
  commits: 4
---

# Phase 01 Plan 03: Query Surface and Concurrency Proof Summary

Every SQL statement the rest of the project will run, in one module with every value bound as a parameter — and the threaded proof that two writers hitting the same file lose neither an error nor an update.

## What Was Built

**`backend/app/db/queries.py`.** Sixteen functions in five sections: profile, positions, trades, snapshots, watchlist, chat. Every one is a plain `def` taking `conn: sqlite3.Connection` first and `user_id` last with a default, so pytest calls them directly with no event loop and app code reaches them through the single `run_db` seam. Nothing in the module opens a connection, closes one, or decides whether a write needs a transaction — the caller wraps writes in `writing()`.

The whole surface lands in one plan on purpose. Phase 3's portfolio work and its watchlist work would otherwise be two agents editing this file in the same wave, and `execute_trade` needs `add_watchlist_ticker` for the rule that trading an unwatched ticker adds it to the watchlist. Deferring the watchlist half to the watchlist plan would have blocked the portfolio plan.

**Rounding lives at the write boundary and is asserted there.** `insert_trade` puts quantity through `round_quantity` and price through `round_money`; `upsert_position` puts both `quantity` and `avg_cost` through `round_quantity`; `update_cash_balance` puts the balance through `round_money`. `test_money.py` already proved the helpers behave — the new tests prove these three functions actually route through them, which is the part a later refactor could quietly drop while every existing test stayed green. `insert_snapshot` deliberately does not round: `total_value` is derived, and the client recomputes it from the price stream on every frame.

**`backend/tests/db/test_concurrency.py`.** Three tests, 1.3 seconds. Six writer threads run twenty read-modify-write cycles each — read `cash_balance`, add one, write it back, all inside one `writing()` block — while three reader threads open plain connections and read the profile concurrently. The assertion that matters is not the empty exception list: it is that the final balance equals `10000 + 1.0 x 120`. Zero errors alone would also be satisfied by a design that silently loses updates; the equality is what proves `BEGIN IMMEDIATE` genuinely serialized the sequences. A second test runs `insert_snapshot` and `insert_trade` threads against the same file and asserts both row counts exactly. A third holds a write lock for 300ms and shows a second writer *waits it out and succeeds* rather than failing instantly — the elapsed time is what distinguishes `PRAGMA busy_timeout` doing the waiting from a retry loop hiding somewhere.

**The canonical ticker list, finally single.** `main.py` now imports `DEFAULT_TICKERS` from `app.db.seed` and starts the market source from it. Plan 01-01 declared the list locally and named 01-02 as the owner; 01-02's own task text handed the rewiring to this plan to avoid a wave-2 merge collision. Both handoff notes are now resolved and the duplicate is gone — this was the one place the streamed ticker set and the seeded watchlist could silently diverge.

## Key Decisions

**`insert_trade` returns the stored `executed_at`.** PLAN.md section 8's trade response carries `executed_at`. With a `None` return, Phase 3 would have generated its own timestamp for the response, giving two timestamps for one trade that differ by however long the write took. Returning the written one costs a line and removes the divergence by construction.

**Every timestamp ordering carries a `rowid` tiebreaker.** This is not defensive garnish. On Windows, CPython 3.12's `time.time()` resolves to roughly 15ms, so three snapshots inserted in a loop genuinely share one `recorded_at` string. `ORDER BY recorded_at DESC` alone would return them in an unspecified order and `get_latest_snapshot` would be a coin flip — the exact situation Phase 3's "skip an unchanged write" check depends on getting right. `ORDER BY recorded_at DESC, rowid DESC` makes insertion order the tiebreak, and the newest-first tests pin it.

**`get_snapshots` is one statement, not two.** The `since` filter is expressed as `AND (? IS NULL OR recorded_at >= ?)` with the value bound twice, rather than branching into a second SQL string. One statement to audit, and the NULL case cannot drift away from the filtered case.

**The held-position rule is not here.** Rejecting removal of a ticker with an open position belongs at Phase 3's service seam, composed from `get_position` and `remove_watchlist_ticker`, where the 409 is raised. Putting it in the storage layer would mean the storage layer knew about HTTP status codes and would make the function untestable in isolation.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `tests/test_main.py` imported `DEFAULT_TICKERS` from `app.main`**

- **Found during:** Task 2
- **Issue:** The wiring change removed `app.main.DEFAULT_TICKERS`, and `tests/test_main.py:17` imported it from there, asserting `source.get_tickers() == DEFAULT_TICKERS`. The import would have failed at collection, taking the whole file down.
- **Root cause (proven, not assumed):** grepped for `DEFAULT_TICKERS` across `backend/` before running anything; the import site was the only consumer.
- **Fix:** the test now imports the constant from `app.db.seed` — the same source `main.py` reads — and compares against `list(DEFAULT_TICKERS)`, since the seed constant is a tuple and `get_tickers()` returns a list. The test docstring records that this now also pins the streamed set against the seeded set.
- **Files modified:** `backend/tests/test_main.py`
- **Commit:** `19b4140`
- **Worth carrying forward:** the assertion is strictly stronger than before — it used to compare `main.py` against itself.

**2. [Rule 3 - Blocking] `source.start()` is typed `list[str]`, `DEFAULT_TICKERS` is a tuple**

- **Found during:** Task 2
- **Issue:** `MarketDataSource.start(tickers: list[str])` in the frozen module declares a list; `app.db.seed.DEFAULT_TICKERS` is `tuple[str, ...]`.
- **Fix:** `main.py` passes `list(DEFAULT_TICKERS)`. Converting at the call site honours the frozen module's declared contract without touching either constant, and the frozen module stays unmodified.
- **Files modified:** `backend/app/main.py`
- **Commit:** `19b4140`

### Adjustment for an acceptance check

**3. Reworded the in-memory note in `test_concurrency.py`**

- **Found during:** verification
- **Issue:** the plan's acceptance criterion is that `test_concurrency.py` "does not contain the string `:memory:`". The module docstring explained *why* an in-memory database is unusable here, and in doing so named the literal.
- **Fix:** the docstring says "an in-memory database" and keeps the full explanation. Behaviour unchanged; the literal check is now unambiguous. Note that `test_connection.py` and `test_seed.py` from plan 01-02 still carry the same literal inside their own explanatory docstrings — also as explanations, not as usage. No test in `tests/db/` opens an in-memory database.
- **Commit:** `e51e788`

No Rule 1, Rule 2 or Rule 4 deviations. Nothing architectural arose.

## Known Stubs

None. Every one of the sixteen functions has a real implementation and at least one test that exercises it against a real file database.

## Threat Flags

None new. The three mitigations this plan owns from the phase threat register are implemented and covered:

| Threat | Mitigation | Evidence |
|--------|-----------|----------|
| T-1-04 (SQL construction) | Every value bound with `?`, including limits and `since` | `grep -cE 'f"(SELECT\|INSERT\|UPDATE\|DELETE)' app/db/queries.py` returns 0; no f-string, `%`-format or concatenation appears in any statement |
| T-1-02 (concurrent writers, lost updates) | `writing()` takes the write lock up front; WAL and `busy_timeout` on every open | `test_concurrent_increments_lose_nothing` — final balance equals start plus increment times 120 commits, not merely zero errors |
| T-1-11 (trade audit log integrity) | `insert_trade` is the only function touching `trades` | `grep -cE "def (update_trade\|delete_trade\|remove_trade\|edit_trade)"` returns 0; the module docstring and `insert_trade`'s docstring both record that nothing here may edit or erase a trade row |
| T-1-05 (ticker symbols reaching SQL) | Nine `normalize_ticker` call sites, one per ticker argument | `test_invalid_ticker_raises`, `test_add_rejects_an_invalid_ticker`, `test_lowercase_ticker_is_stored_uppercased`, `test_add_normalizes_the_ticker` |

T-1-12 (chat content stored in plaintext) stays `accept` as registered.

## Verification

All checks run from `backend/`.

| Check | Result |
|-------|--------|
| `uv run --extra dev pytest -q` (full suite) | **243 passed**, 0 failed |
| `uv run --extra dev pytest -q tests/db/test_queries.py -x` | 37 passed (plan required at least 20) |
| `uv run --extra dev pytest -q tests/db/test_concurrency.py -x` | 3 passed (plan required at least 3) |
| `uv run --extra dev pytest -q tests/db` | 73 passed in **3.56s** (plan budget: under 15s) |
| `uv run --extra dev pytest -q tests/test_main.py tests/api` | 13 passed — the `main.py` rewire did not disturb app assembly |
| `uv run --extra dev ruff check app/ tests/` | All checks passed |
| `git status --porcelain backend/app/market/` | empty — frozen module untouched |
| `git status --porcelain backend/tests/market/` | empty — no pre-existing market test edited |

**Regression gate (D-24):** plan 01-02 left the suite at 203 passing. It now runs 243 (203 + 40 new) with zero failures. No test that passed before this plan fails now.

**On the known flake.** `tests/market/test_simulator_source.py::test_custom_update_interval` failed on the first full-suite run and passed on the second, unchanged. It is a timing assertion inside the frozen `backend/app/market/` module, flagged as pre-existing in the wave-2 handoff, and `git status --porcelain backend/app/market/` confirms nothing in that module was touched by this plan. Not investigated, per the handoff instruction. Worth noting for whoever eventually owns it: it also failed once *in isolation* under `pytest -q` and passed moments later under the same selection without `-q`, so "passes in isolation" is not a reliable characterisation — it is simply timing-sensitive.

**Acceptance greps.**

| Check | Result |
|-------|--------|
| f-string SQL in `queries.py` | 0 |
| `async def` in `queries.py` | 0 — every function is a plain `def` |
| trade update/delete helpers | 0 |
| `normalize_ticker` occurrences | 9 |
| `:memory:` in `test_concurrency.py` | 0 |

## Requirements Satisfied

| ID | Evidence |
|----|----------|
| CORE-04 | The query surface runs against the lazily-initialized, seeded schema: every test in `test_queries.py` drives a real file database created by `apply_schema` + `seed_fresh`, and `test_seeded_watchlist_holds_the_default_tickers` ties the query layer to the seed |
| CORE-05 | `test_concurrency.py` — six writers plus three readers with zero `OperationalError`, final value equal to the committed write count, and a blocked writer that waits out a held `BEGIN IMMEDIATE` instead of failing |
| CORE-10 | Every function in `queries.py` is a plain `def` taking the connection first, so all database work still crosses the single `run_db` offload; `grep` for `async def` in the module returns 0 |
| TEST-01 | 40 new tests. The trade log's append-only property is enforced structurally (no mutating helper exists) and its write-boundary rounding is asserted directly by `test_insert_trade_rounds_at_the_write_boundary` |

## Notes for Future Phases

- **`add_watchlist_ticker` returns `True` only when a row was actually added.** Phase 3's trade path can use the return to tell the user "and added AAPL to your watchlist" without a second query.
- **`remove_watchlist_ticker` returning `False` is your 404.** The 409 for a held position is composed above this layer: check `get_position` first, then remove.
- **Wrap writes in `writing()`, leave reads bare.** The concurrency tests only hold under `BEGIN IMMEDIATE`; a read-modify-write outside it will lose updates and nothing will raise.
- **Do not assume distinct timestamps.** Two rows written in the same 15ms window share a `recorded_at`. Order by the timestamp *and* `rowid`, or use the functions here which already do.
- **`insert_trade` gives you the timestamp.** Do not generate a second one for the response.
- **`insert_chat_message` takes `actions` as an already-serialized JSON string or `None`.** This module never imports `json`; serialization is the chat service's call.
- **`main.py` no longer defines `DEFAULT_TICKERS`.** Import it from `app.db.seed`, and convert to a list when handing it to `source.start()`.

## Self-Check: PASSED

All three created files and all three modified files exist on disk and are tracked by git. All four task commits (`83ae3e3`, `19b4140`, `469468b`, `e51e788`) are present in `git log`. `backend/app/market/` and `backend/tests/market/` are unmodified.

**Note on `actuals.tokens`:** 9,000 is chars/4 over the 32,174 characters in the three new files plus roughly 3,900 characters of change across the three modified ones. Against the plan's estimate of 80,000 the authored work again came in an order of magnitude under — the third consecutive plan in this phase to do so, which is now a pattern rather than an outlier: the estimates are sized for total phase context, not diff volume.
