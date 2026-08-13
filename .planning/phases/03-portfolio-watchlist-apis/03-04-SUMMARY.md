---
phase: 03-portfolio-watchlist-apis
plan: 04
subsystem: backend-services-api
status: complete
tags: [watchlist, fastapi, sqlite, service-seam, market-data, tdd]

requires:
  - "backend/app/db/ (Phase 1) — run_db, writing, get_watchlist, add_watchlist_ticker, remove_watchlist_ticker, get_position"
  - "backend/app/market/ (frozen) — PriceCache, MarketDataSource, normalize_ticker"
  - "backend/app/services/errors.py (03-01) — Conflict, NotFound"
  - "backend/app/api/models.py (03-01) — WatchlistResponse, WatchlistTickerOut, WatchlistAddRequest"
  - "backend/app/api/errors.py (03-01) — the bare-ValueError handler that makes an invalid symbol a 400"
provides:
  - "services.watchlist.add — the published cross-phase watchlist add seam (Phase 6 CHAT-08)"
  - "services.watchlist.remove — the published cross-phase watchlist remove seam (Phase 6 CHAT-09)"
  - "services.watchlist.read_watchlist and quote — the one null rule for a priceless ticker"
  - "services.watchlist.TickerQuote, WatchlistEntry"
  - "GET /api/watchlist, POST /api/watchlist, DELETE /api/watchlist/{ticker}"
  - "tests/services/conftest.py RecordingSource — a MarketDataSource fake for any later service test"
affects:
  - "03-05 (reconciles app/services/__init__.py; must export the watchlist seam)"
  - "Phase 4 frontend (the three route shapes are its contract)"
  - "Phase 6 (routes LLM watchlist changes through add/remove)"

tech-stack:
  added: []
  patterns:
    - "Composed unit of work: a plain def passed to run_db, opening writing(conn) once"
    - "Check-and-delete inside a single BEGIN IMMEDIATE rather than a read then a write"
    - "Router factory taking its collaborators, mirroring create_health_router"
    - "Dataclass returned straight from a handler; response_model does the shaping"

key-files:
  created:
    - backend/app/services/watchlist.py
    - backend/app/api/watchlist.py
    - backend/tests/services/conftest.py
    - backend/tests/services/test_watchlist.py
    - backend/tests/api/test_watchlist.py
  modified:
    - backend/app/main.py
    - backend/app/api/__init__.py

decisions:
  - "remove takes no MarketDataSource, per the locked option-a contract and D-08"
  - "The held-position check and the delete share one writing() block, not two calls"
  - "The database write precedes source registration, so a failed feed self-heals on next boot"
  - "RecordingSource lives in tests/services/conftest.py, and the failing variant is a second fixture rather than an imported class"

metrics:
  duration: "~25 min"
  completed: 2026-08-13
  tasks: 2
  commits: 4

actuals:
  tokens: 6600
  tasks: 2
  commits: 4

requirements: [WATCH-01, WATCH-02, WATCH-03, WATCH-04, WATCH-05, WATCH-06]
---

# Phase 3 Plan 04: Watchlist Service and Routes Summary

The watchlist is now a rule-enforced resource end to end: readable with live price,
open price, change-from-open and up to 60 sparkline points; addable through the one
shared ticker rule and registered with the running market source; removable, rejected
409 when a position is held and 404 when the ticker was never watched.

## What Was Built

**The service seam (`backend/app/services/watchlist.py`, 165 lines).** Three public
functions plus the null rule.

`add(db_path, source, ticker) -> WatchlistEntry` and `remove(db_path, ticker) -> None`
are implemented exactly as `03-SEAM-CONTRACT.md` locks them — option-a, with the
deliberate asymmetry intact. `add` normalizes first (so a malformed symbol does no
I/O at all), then writes the row through `run_db`, then registers with the source,
in that order per D-09. `remove` normalizes, then hands `_remove_checked` to `run_db`
and touches no market source.

`_remove_checked` is where D-08 lives: `get_position` and `remove_watchlist_ticker`
run inside one `with writing(conn):` block, so a position created concurrently cannot
slip between the check and the delete. Both raises happen inside the block, which is
required rather than incidental — `writing()` rolls back and re-raises, so a rejected
removal commits nothing. Held is checked before the delete, which is what makes the
DELETE decision order 400 → 409 → 404 → 204.

`quote(cache, ticker)` is the single place the null rule lives. No cached price means
all three numeric fields are `None` and `history` is `[]`; a price at its session open
means `change_from_open_percent == 0.0`. Every number is passed through untouched —
the percentage is read from the `PriceUpdate` property rather than recomputed, so this
plan introduces no second rounding rule. `read_watchlist` maps `quote` over the rows
`get_watchlist` returns and imposes no ordering of its own.

The module contains zero SQL, zero regular expressions and no FastAPI import.

**The routes (`backend/app/api/watchlist.py`, 62 lines).** `create_watchlist_router(price_cache, source)`
carries all three routes and catches nothing. GET returns `{"tickers": [...]}` of
`TickerQuote` dataclasses straight into `response_model=WatchlistResponse`. POST hands
the raw body value to the service and answers with `quote(price_cache, entry.ticker)`,
so a lowercase request answers with the uppercase form. DELETE is `status_code=204,
response_model=None` and returns nothing.

**The wiring.** `main.py` gained one import and one `include_router` call, placed after
every other router and immediately above `app.frontend(...)`, which remains the last
statement before `return app`. `tests/test_main.py::test_api_not_shadowed` was run
directly and still passes.

**The tests.** `RecordingSource` (a `MarketDataSource` fake implementing all six
abstract members) plus `recording_source` and `failing_source` fixtures; 22 service
tests and 12 route tests.

## Key Decisions

**The failing source is a fixture, not an imported class.** The plan's acceptance
criterion is phrased as `RecordingSource(fail_on_add=True)`. Importing the class from
a `conftest` module across the test package boundary works but is fragile to how
pytest names conftest modules, so `failing_source` was added as a second fixture
returning exactly that instance. The class is still importable and the service test
module does import it for its type annotations.

**GET returns dataclasses, not hand-built models.** FastAPI's `_prepare_response_content`
recurses through the returned dict and list and calls `dataclasses.asdict` on each
`TickerQuote`, so `response_model=WatchlistResponse` validates them into
`WatchlistTickerOut` with no `from_attributes` configuration and no duplicate
construction code. Verified against the installed FastAPI 0.141.1 / Pydantic 2.12.5 by
the passing route tests, which assert the exact null-vs-zero shape of the payload.

**`_add_row` wraps a single statement in `writing()` anyway.** `add_watchlist_ticker`
is one `INSERT ... ON CONFLICT DO NOTHING` and would be safe under autocommit, but
every write in this phase going through one `BEGIN IMMEDIATE` shape is worth more than
the saved line: it means no reader of this module has to work out which writes are
transactional and which are not.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `uv` could not hardlink into the OneDrive-backed worktree**

- **Found during:** Task 1 verification
- **Issue:** the worktree had no `.venv`, and creating one hit the `os error 396`
  hardlink failure PROJECT.md records as an accepted OneDrive risk — the same one
  03-01 hit.
- **Fix:** ran every command with `UV_LINK_MODE=copy`, as the orchestrator's
  environment note directs. Environment-only; no file changed and nothing was added
  to the repo.
- **Files modified:** none
- **Commit:** n/a

No other deviations. Both tasks were executed as written, including the option-a
signatures, the D-08 single-transaction removal and the D-09 write-then-register
ordering.

## Verification

| Check | Result |
|---|---|
| `pytest tests/services/test_watchlist.py -q` | 22 passed (criterion: >= 15) |
| `pytest tests/api/test_watchlist.py -q` | 12 passed (criterion: >= 9) |
| `pytest tests/test_main.py -q` | 6 passed, `test_api_not_shadowed` included |
| `pytest tests/services tests/api -q` (the plan's gate) | 46 passed |
| `ruff check app/ tests/` | All checks passed |
| `grep -c "INSERT INTO\|DELETE FROM\|UPDATE " app/services/watchlist.py` | 0 |
| `grep -c "HTTPException" app/services/watchlist.py` | 0 |
| `grep -c "with writing(conn):" app/services/watchlist.py` | 2 |
| `grep -c "HTTPException\|try:" app/api/watchlist.py` | 0 |
| OpenAPI watchlist paths | `['/api/watchlist', '/api/watchlist/{ticker}']` |
| `git diff --name-only <base> HEAD` | exactly the 7 declared files |
| `git status` | `db/finally.db` unmodified; no change to `app/db/`, `app/market/`, `api/models.py`, `services/__init__.py`, `services/trading.py`, `services/portfolio.py`, `api/portfolio.py`, `pyproject.toml`, `uv.lock` |

The full-suite gate is deliberately not run here: the plan scopes verification to
`tests/services tests/api` because three wave-2 plans execute against the same tree,
and 03-05 Task 4 owns the full-suite run in wave 3.

## TDD Gate Compliance

Both tasks ran RED before GREEN, and the gate sequence is visible in git log:

| Task | RED | GREEN |
|---|---|---|
| 1 (service) | `0063ffd` — collection failed on `No module named 'app.services.watchlist'` | `1b8d265` — 22 passed |
| 2 (routes) | `91e8404` — 11 failed, 1 passed | `d49bacb` — 18 passed |

No REFACTOR commit was needed; neither module required cleanup after going green.

Task 2's RED had one passing test by design: `TestMountOrder::test_health_still_answers`
asserts pre-existing behavior that the new router must not break, so it correctly
passed before the router existed.

## Known Stubs

None. Every function this plan declares is fully implemented, every route is wired,
and no response carries a hardcoded or placeholder value.

One deliberate non-implementation, recorded so it is not read as an omission:
`MarketDataSource.remove_ticker` stays uncalled in Phase 3. That is D-08's decision,
not an unfinished edge — `remove` removes only the database row, and the docstring on
`services.watchlist.remove` states why.

## Threat Flags

No new security-relevant surface beyond the plan's `<threat_model>`. The three new
endpoints, their ticker inputs and their SQLite writes are covered by T-03-10 through
T-03-15, and each mitigation is present: `normalize_ticker` first in both `add` and
`remove`, the check-and-delete inside one `writing(conn)`, the `include_router` call
above `app.frontend(...)` with `test_api_not_shadowed` passing, `{"detail": str(exc)}`
never a repr, and no `user_id` in any route, model or service signature.

## Flagged Assumptions Resolved As Planned

All three `unclassified` probe rows were implemented per the planner's reading and are
now proven in behavior rather than assumed:

- **WATCH-02** — `normalize_ticker` from `app.market` is the only rule; the 400 comes
  from the bare-`ValueError` handler, asserted by
  `test_an_invalid_symbol_is_a_400_not_a_422`.
- **WATCH-03** — registration is proven twice, by `RecordingSource` asserting the call
  and its ordering against the row, and by
  `test_a_started_simulator_produces_a_price_for_an_added_ticker`, which starts a real
  `SimulatorDataSource` and asserts `cache.get_price("PYPL") is not None`.
- **WATCH-06** — the DELETE decision order 400 → 409 → 404 → 204 is asserted by four
  separate route tests.

## Self-Check: PASSED

All five created files verified present on disk. All four commits verified in
`git log`: `0063ffd`, `1b8d265`, `91e8404`, `d49bacb`.
