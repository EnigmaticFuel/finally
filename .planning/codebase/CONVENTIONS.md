# Coding Conventions

**Analysis Date:** 2026-08-04

> Source of truth: `backend/app/market/` and `backend/tests/market/` are the only built code
> in this repo and set the house style every future phase (portfolio, watchlist, chat,
> frontend) must match. Root `CLAUDE.md` and `backend/CLAUDE.md` state additional rules that
> are **mandatory**, not merely observed — they are called out explicitly below.

## Mandatory Rules (from CLAUDE.md — not optional)

These come from the user's global `CLAUDE.md` and are enforced project-wide:

- **No defensive programming.** Do not wrap code in speculative `try/except` "just in case."
  The one `except Exception` in this codebase (`simulator.py` `_run_loop`) is justified with a
  comment explaining exactly why: an unhandled exception in a background task kills the price
  feed silently. Every other error path uses `ValueError` raised deliberately, not caught broadly.
- **No emojis** — never in code, print statements, log messages, docstrings, or comments.
- **Short modules, short functions.** Every file in `app/market/` is under 200 lines and does
  one thing (`cache.py` = storage, `models.py` = data shape, `simulator.py` = GBM math + task
  wrapper, `stream.py` = SSE generator, `tickers.py` = one regex, `seed_prices.py` = static data
  + one hash function). Split a module before it grows past this size.
- **Docstrings over inline comments.** Every module, class, and public function has a
  docstring explaining purpose and non-obvious behavior. Inline `#` comments are reserved for
  explaining *why*, not *what* — see `simulator.py:298-302` for the pattern: a comment justifying
  a deliberately broad exception catch, not restating the code.
- **Identify root cause before fixing.** Applies to future debugging work in this codebase, not
  just this document.
- **Use `uv`, never bare `python`/`pip`.** `uv run pytest`, `uv add <package>`,
  `uv sync --extra dev`. Never `python3 -m pytest` or `pip install`.
- **Use latest library APIs** — the codebase already does this (see below).

## Naming Patterns

**Files:**
- One module per responsibility, `lowercase_with_underscores.py`: `cache.py`, `models.py`,
  `interface.py`, `simulator.py`, `stream.py`, `tickers.py`, `factory.py`, `seed_prices.py`.
- Test files mirror the module they test 1:1: `app/market/cache.py` → `tests/market/test_cache.py`.
- A conformance suite that must pass for *every* implementation of an interface gets its own file
  named for the contract, not the implementation: `tests/market/test_conformance.py` (see Testing
  Patterns below — reuse this pattern for any future interface with multiple implementations).

**Classes:**
- PascalCase. Concrete implementations are named `<Thing><Role>`: `SimulatorDataSource`,
  `MassiveDataSource`, `GBMSimulator`. Test classes are named `Test<UnitUnderTest>`:
  `TestPriceCache`, `TestWaitForPrice`, `TestGenerateEvents`.

**Functions & variables:**
- `snake_case` throughout. Private/internal methods and module-level helpers prefixed with a
  single underscore: `_run_loop`, `_seed`, `_record_history`, `_generate_events`,
  `_add_internal`, `_rebuild_cholesky`, `_pairwise_correlation`.
- Boolean-returning or predicate-style helpers read as questions where natural
  (`is_disconnected`), but this codebase mostly favors direct nouns/verbs (`get_price`,
  `normalize_ticker`) over `is_`/`has_` prefixes — match existing names in the module you're
  extending rather than inventing a new style.

**Types:**
- `dataclass(frozen=True, slots=True)` for immutable value objects (`PriceUpdate` in
  `backend/app/market/models.py`). `frozen=True` because instances are shared across threads/tasks
  and must never be mutated after construction; `slots=True` for the memory/perf win on a type
  created many times per second.
- Abstract base classes via `abc.ABC` + `@abstractmethod` for anything with multiple
  implementations (`MarketDataSource` in `backend/app/market/interface.py`). The docstring on the
  ABC documents the full lifecycle contract (`start` → `add_ticker`/`remove_ticker` → `stop`), not
  just each method in isolation — write the lifecycle story once, on the class.
- Module-level constants in `SCREAMING_SNAKE_CASE`: `HISTORY_POINTS`, `TRADING_SECONDS_PER_YEAR`,
  `DEFAULT_DT`, `TICKER_PATTERN`.

## Code Style

**Formatting & linting:**
- `ruff` is the only configured tool (`backend/pyproject.toml`), rule set `["E", "F", "I", "N", "W"]`
  (pyflakes, pycodestyle errors/warnings, isort, pep8-naming). `E501` (line too long) is explicitly
  ignored — deferred to a formatter, not manually wrapped.
- `line-length = 100`, `target-version = "py312"`.
- Run: `uv run --extra dev ruff check app/ tests/`. No `black`/`ruff format` config present —
  don't assume auto-formatting runs; write ruff-clean code by hand.
- `from __future__ import annotations` is the first import in every module — always add it to new
  modules for postponed evaluation of type hints.

**Type hints:**
- Full type hints on every function signature, including private helpers and test fixtures where
  practical. Modern union syntax (`float | None`, not `Optional[float]`) throughout — this is the
  "latest library APIs" / Python 3.12+ house style.

**Latest APIs:**
- `numpy` used with modern vectorized calls (`np.random.standard_normal`, matrix `@` multiply) —
  no manual loops where numpy can batch the operation (see `GBMSimulator.step` in
  `backend/app/market/simulator.py`).
- `asyncio.create_task(..., name="simulator-loop")` — tasks are named for observability.

## Import Organization

**Order** (enforced by ruff's `I` / isort rule):
1. `from __future__ import annotations` (always first, own line)
2. Standard library (`asyncio`, `logging`, `math`, `random`, `time`, `hashlib`, `re`)
3. Third-party (`numpy as np`, `fastapi`, `pytest`)
4. Local/relative (`.cache`, `.interface`, `.seed_prices`) — relative imports (`.`) within
   `app/market/`, never absolute `app.market.x` imports between sibling modules in the same
   package.

**No path aliases.** Plain relative imports within a package (`from .cache import PriceCache`);
absolute `from app.market import ...` only from outside the package (tests, other subsystems).
The package `__init__.py` (`backend/app/market/__init__.py`) re-exports the public surface
explicitly via `__all__` — every new public name added to a module must also be added to the
package's `__init__.py` and `__all__` list, and documented in the module docstring's "Public API"
list. Internal helpers (leading underscore) are never re-exported.

## Error Handling

- **Raise, don't swallow.** Validation failures raise plain `ValueError` with a **user-facing
  message written to be shown verbatim** (see `tickers.py: normalize_ticker`, `cache.py:
  wait_for_price`). Callers at the API boundary translate `ValueError` → HTTP 400. This keeps
  domain code free of HTTP concerns.
- **One broad `except Exception` exists, and it is justified in a comment.** In
  `simulator.py: _run_loop`, the background task loop catches all exceptions, logs with
  `logger.exception(...)`, and continues to the next tick — because a background asyncio task
  that dies silently "takes the whole price feed with it, leaving a UI that looks connected and
  frozen." This is the *only* acceptable pattern for broad exception handling in this codebase:
  a long-running background loop where a crash would be invisible and catastrophic. Do not use
  broad `except` anywhere else — this is not a general defensive-programming license.
- **Degrade rather than crash on unreachable-but-possible failure**, with a `logger.error` and an
  explanit comment: see `simulator.py: _rebuild_cholesky`'s `LinAlgError` fallback to independent
  draws. Document why the branch is believed unreachable and what the safe fallback is.
- Idempotent lifecycle methods (`stop()`) tolerate being called when already stopped/never
  started — checked with plain `if` guards, not try/except.

## Logging

- Standard library `logging`, one `logger = logging.getLogger(__name__)` per module.
- **No emojis, ever**, in log messages.
- `logger.info` for lifecycle events (start/stop/add/remove ticker, client connect/disconnect).
- `logger.debug` for high-frequency internal events (simulator shock events).
- `logger.exception` (not `logger.error`) when inside an `except` block, so the traceback is
  captured — see `simulator.py: _run_loop`.
- `logger.error` for a defended-against-but-unreachable condition — see
  `simulator.py: _rebuild_cholesky`.
- Use `%s`-style lazy formatting, not f-strings, in log calls: `logger.info("Simulator started
  with %d tickers", len(tickers))`.

## Comments

- **Docstrings carry the "why," not inline comments.** Module docstrings state the module's
  single responsibility. Class docstrings state the full contract/lifecycle, including math
  formulas where relevant (`GBMSimulator`'s docstring includes the GBM equation itself). Method
  docstrings explain non-obvious behavior and invariants (e.g., `PriceCache.update`: "The first
  update for a ticker pins its session baseline").
- Inline `#` comments are rare and reserved for explaining a specific non-obvious choice at that
  exact line — a magic constant's derivation (`simulator.py:24-26`, the trading-seconds-per-year
  math), or why an exception is being caught broadly. If a comment would just restate the next
  line of code, delete it.

## Function Design

- **Size:** functions stay small and single-purpose; the largest function in the market module
  (`GBMSimulator.step`) is ~35 lines including its docstring.
- **Pure vs. I/O separated deliberately.** `GBMSimulator` (in `simulator.py`) is explicitly "pure
  and synchronous: holds prices, parameters and the Cholesky factor, and knows nothing about the
  cache, asyncio or FastAPI" — so tests can drive `step()` directly without an event loop or
  mocking. `SimulatorDataSource` is the thin async wrapper that owns the task and touches the
  cache. **Apply this split to any future compute-heavy logic**: keep the math/logic class
  synchronous and cache/IO-free, and wrap it in a thin async adapter that owns the task and side
  effects.
- **Parameters:** keyword defaults for tunables that tests need to override (`update_interval`,
  `event_probability`, `history_points`, `history_interval`) so tests can use small/zero values
  instead of sleeping or waiting for real-world timers.
- **Return values:** prefer returning plain dicts/dataclasses over mutating passed-in state where
  practical; `PriceCache.update()` both stores and returns the `PriceUpdate` it created.

## Module Design

- **Explicit `__all__` in the package `__init__.py`**, with a docstring "Public API" list that
  matches it exactly (`backend/app/market/__init__.py`). This is the pattern to replicate for
  every future subsystem package (`app/portfolio/`, `app/watchlist/`, `app/chat/`).
- **Interface + factory pattern for swappable implementations.** `MarketDataSource` (ABC) +
  `SimulatorDataSource` / `MassiveDataSource` (implementations) + `create_market_data_source()`
  (factory, env-var driven, in `backend/app/market/factory.py`). Downstream code depends only on
  the interface, never on a concrete implementation. Apply this pattern anywhere the plan calls
  for pluggable behavior (e.g. mock vs. real LLM client).
- **Router factories, not module-level routers.** `create_stream_router(price_cache)` builds and
  returns an `APIRouter` bound to a specific cache instance, rather than declaring the router at
  import time — this avoids double-registration when a test app and the real app are both built
  in the same process. Every future FastAPI router (portfolio, watchlist, chat) should follow
  this factory-function shape, taking its dependencies (cache, db connection, LLM client) as
  constructor arguments rather than importing globals.
- **One shared validation rule, one place.** Ticker validation lives in exactly one function
  (`normalize_ticker` in `tickers.py`) and every caller — manual API and future LLM-driven
  trades/watchlist changes alike — must import and call it rather than re-implementing the regex.

---

*Convention analysis: 2026-08-04*
