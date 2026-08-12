---
phase: 03-portfolio-watchlist-apis
type: outline
created: 2026-08-12
plans: 5
waves: 3
requirements_total: 21
edges_total: 44
---

# Phase 3 — Plan Outline

Chunked planning. `03-01-PLAN.md` is already written and is FIXED; rows 2-5 are authored in
per-plan runs against this outline. Every plan expands on the seams `03-01` establishes and
none re-derives them.

| Plan ID | Objective | Wave | Depends On | Requirements |
|---------|-----------|------|------------|--------------|
| 03-01 | One successful buy travels router → service → `run_db` → a single `BEGIN IMMEDIATE` transaction and back out as a response carrying the server-side `fill_price`, publishing the `execute_trade` seam and the full Pydantic model surface. **(already written — do not re-plan)** | 1 | — | PORT-02, PORT-07, PORT-10, PORT-11 |
| 03-02 | The trade rule set is complete and provably enforced: sells settle cash and shares, and every rejection branch — insufficient cash, insufficient shares, bad quantity, no-price-yet — returns a 400 the user can read, with a sell to zero deleting the position row. | 2 | 03-01 | PORT-03, PORT-04, PORT-05, PORT-06, PORT-08, PORT-09, TEST-02 |
| 03-03 | The portfolio is readable and resettable: `GET /api/portfolio` reports cash, live-valued positions and total value, `GET /api/portfolio/history` serves bounded snapshot history, and `POST /api/portfolio/reset` returns cash to `STARTING_CASH` with no positions and a snapshot marking the step. | 2 | 03-01 | PORT-01, PORT-13, PORT-14 |
| 03-04 | The watchlist is a real, rule-enforced resource: read with live price, open price, change-from-open and ~60 sparkline points; add validated by the shared ticker rule and registered with the running market source; remove rejected 409 when held and 404 when unwatched. | 2 | 03-01 | WATCH-01, WATCH-02, WATCH-03, WATCH-04, WATCH-05, WATCH-06 |
| 03-05 | Portfolio value accumulates on its own: a lifespan-owned `snapshot-loop` task records total value every 30 seconds and skips the write when the cents-rounded total is unchanged — and the phase's public API surface and full test suite are reconciled green. | 3 | 03-02, 03-03, 03-04 | PORT-12 |

## Notes

### Parallel-safe plans

**Wave 2 — `03-02`, `03-03` and `03-04` run in parallel.** Their `files_modified` sets are
pairwise disjoint (verified below). This is the ROADMAP's own decomposition made concrete:
"the portfolio and watchlist work are disjoint modules and can run as parallel plan waves."
`03-02` (trade rules) and `03-03` (portfolio read/reset/history) split the portfolio side by
module — one owns `services/trading.py`, the other owns `services/portfolio.py` and the
portfolio router — so they too are parallel rather than sequential.

**Wave 3 — `03-05` alone.** It is serialized behind wave 2 for exactly one reason: it is the
third writer of `backend/app/main.py` (after `03-01` in wave 1 and `03-04` in wave 2), and it
reconciles `backend/app/services/__init__.py` against everything the wave-2 plans published.

### File-level ownership boundaries

No file is written by two plans in the same wave. Every multi-wave file is listed with the
waves that touch it, so a per-plan run can see at a glance what it may claim.

| File | 03-01 (W1) | 03-02 (W2) | 03-03 (W2) | 03-04 (W2) | 03-05 (W3) |
|------|:---:|:---:|:---:|:---:|:---:|
| `backend/app/services/errors.py` | own | — | — | — | — |
| `backend/app/api/models.py` | own (all 9 models) | — | — | — | — |
| `backend/app/api/errors.py` | own | — | — | — | — |
| `backend/app/services/trading.py` | create | **extend** | — | — | — |
| `backend/app/services/portfolio.py` | create (`value_portfolio`) | — | **extend** | — | — |
| `backend/app/api/portfolio.py` | create (trade route) | — | **extend** (3 routes) | — | — |
| `backend/app/services/watchlist.py` | — | — | — | **create** | — |
| `backend/app/api/watchlist.py` | — | — | — | **create** | — |
| `backend/app/services/snapshots.py` | — | — | — | — | **create** |
| `backend/app/api/__init__.py` | edit | — | — | **edit** | — |
| `backend/app/services/__init__.py` | create | — | — | — | **reconcile** |
| `backend/app/main.py` | edit | — | — | **edit** (watchlist router) | **edit** (snapshot task) |
| `backend/tests/services/test_trading.py` | create | **extend** | — | — | — |
| `backend/tests/services/test_portfolio.py` | — | — | **create** | — | — |
| `backend/tests/services/test_watchlist.py` | — | — | — | **create** | — |
| `backend/tests/services/test_snapshots.py` | — | — | — | — | **create** |
| `backend/tests/services/conftest.py` | — | — | — | **create** (fake source) | — |
| `backend/tests/api/test_portfolio.py` | create | — | **extend** | — | — |
| `backend/tests/api/test_watchlist.py` | — | — | — | **create** | — |
| `backend/tests/conftest.py` | — | — | — | — | **edit** (one line) |
| `backend/tests/test_main.py` | — | — | — | — | **edit** (task-name assert) |

Boundary rules the per-plan runs must honor:

- **`app/api/models.py` is closed after `03-01`.** All nine response/request models are
  published there by `03-01` Task 3 precisely so the three wave-2 plans never edit one shared
  file. A wave-2 plan that believes it needs a new model has found a scope error, not a
  missing model.
- **`app/db/` is frozen for the whole phase** — `queries.py`, `connection.py`, `money.py`,
  `seed.py`, `schema.sql`. No plan lists any of them in `files_modified`. PORT-14's missing
  bulk delete is composed from `get_positions` + `delete_position` in a loop inside one
  `writing()` block (RESEARCH Open Question 1); it is not a new query function.
- **`app/market/` is frozen.** Consumed only through `PriceCache`, `wait_for_price`,
  `normalize_ticker` and `MarketDataSource`.
- **`app/services/__init__.py` deliberately lags during wave 2.** Wave-2 plans import from
  submodules directly (`from app.services.watchlist import add`) and do not touch the package
  `__init__`. `03-05` publishes the final Public API docstring and `__all__` in one pass, which
  is what keeps three parallel plans off one file. Note this in each wave-2 plan so an executor
  does not "helpfully" update it.
- **`app/main.py` is the only Phase 1 file any plan edits**, and only twice more: `03-04` adds
  the watchlist router above the `app.frontend(...)` line, `03-05` adds the `snapshot-loop`
  task to the lifespan. `app.frontend(...)` stays the last call before `return app` in both
  (C-17, guarded by `tests/test_main.py::test_api_not_shadowed`).
- **`tests/conftest.py`'s one-line `application.state.db_path = db_path` belongs to `03-05`
  alone** (RESEARCH Pitfall 1). It is only load-bearing once a lifespan-owned background task
  exists, and pairing it with the sleep-first loop ordering means correctness does not rest on
  the fixture edit alone. It must be an explicit task with its rationale, not an incidental
  edit — Phase 1's D-22 says these fixtures are reused verbatim.

### Edge distribution across plans

All 44 rows in `03-EDGE-COVERAGE.json` are attributed by `requirement_id`, so no requirement's
edges are orphaned. Resolution and `must_haves` authoring happen in the per-plan runs.

| Plan ID | Edges | By requirement |
|---------|------:|----------------|
| 03-01 | 8 | PORT-02 (2), PORT-07 (1), PORT-10 (2), PORT-11 (3) — **already lifted into `03-01`'s `must_haves`; do not re-attribute** |
| 03-02 | 13 | PORT-03 (2), PORT-04 (2), PORT-05 (1), PORT-06 (2), PORT-08 (2), PORT-09 (1), TEST-02 (3) |
| 03-03 | 8 | PORT-01 (5), PORT-13 (2), PORT-14 (1) |
| 03-04 | 12 | WATCH-01 (5), WATCH-02 (1), WATCH-03 (1), WATCH-04 (2), WATCH-05 (2), WATCH-06 (1) |
| 03-05 | 3 | PORT-12 (3) |
| **Total** | **44** | 8 resolved-in-place by `03-01`, 36 to lift across `03-02`..`03-05` |

Five rows arrive `unclassified` (PORT-05, PORT-09, PORT-14, WATCH-02, WATCH-03, plus PORT-07
already handled in `03-01`). Those per-plan runs must record a planner reading in a "Flagged
assumptions" section rather than dropping the row, in the shape `03-01` established.

### Sizing and scope notes for the per-plan runs

- **`03-02` carries seven requirements but one module.** They are six branches of the same
  `_apply_trade` / `validate_quantity` surface plus the aggregate TEST-02 suite over them; the
  cohesion is real, not a bundle of convenience. Two things it must NOT do: reopen the
  `execute_trade` signature (`03-01` Task 1 locked it as the Phase 6 contract), or restructure
  the transaction — the sell branch replaces exactly the one stub line `03-01` left for it.
- **`03-04` carries six requirements across three endpoints.** Splitting it would put two plans
  on `services/watchlist.py` and `api/watchlist.py` and force them into separate waves, which
  costs the parallelism the ROADMAP explicitly asked for. Keep it whole.
- **`03-05` looks small at one requirement but is not**: a new service module, the lifespan
  wiring, the conftest fix, the `test_main.py` task-name assertion, the `services/__init__.py`
  reconciliation, and the phase-wide green-suite gate. CONTEXT.md `<deferred>` also releases the
  snapshot-task-versus-`execute_trade` collision test into this phase — `03-05` is where both
  callers finally exist, so it is the natural owner.
- **Every plan needs its own `<threat_model>`** (ASVS L1, block on `high`). `03-01`'s register
  is the reference shape; wave-2 and wave-3 plans carry the threats their own surface
  introduces, not a copy of `03-01`'s.
- **Zero packages are installed in this phase.** `backend/pyproject.toml` and `backend/uv.lock`
  appear in no plan's `files_modified`. A plan that appears to need `uv add` has found a scope
  error.
- **Regression gate for every plan:** `cd backend && uv run --extra dev pytest -q` at
  >= 243 + new tests, tolerating only the known
  `tests/market/test_simulator_source.py::test_custom_update_interval` flake, plus
  `uv run --extra dev ruff check app/ tests/` exiting 0.

## OUTLINE COMPLETE
