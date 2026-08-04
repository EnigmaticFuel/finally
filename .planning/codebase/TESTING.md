# Testing Patterns

**Analysis Date:** 2026-08-04

> Source of truth: `backend/tests/market/` (1,437 lines across 9 files) is the only test suite
> in this repo and defines the house testing style for every future backend phase.

## Test Framework

**Runner:**
- `pytest` 8.3+, config in `backend/pyproject.toml` under `[tool.pytest.ini_options]`
  - `testpaths = ["tests"]`
  - `python_files = ["test_*.py"]`
  - `python_classes = ["Test*"]`
  - `python_functions = ["test_*"]`
  - `asyncio_mode = "auto"` — async test functions run without a `@pytest.mark.asyncio`
    decorator on the function itself, but **classes containing async tests are still marked**
    with `@pytest.mark.asyncio` at the class level in this codebase (see `test_cache.py`,
    `test_stream.py`, `test_conformance.py`) — follow that pattern for consistency even though
    auto mode would work without it.
  - `asyncio_default_fixture_loop_scope = "function"`

**Plugins:**
- `pytest-asyncio` 0.24+ — async test support (see above)
- `pytest-cov` 5.0+ — coverage reporting
- `ruff` 0.7+ — lint, not a test tool, but run alongside tests in CI-equivalent local checks

**Fixtures:**
- `backend/tests/conftest.py` defines exactly one fixture: `event_loop_policy`, pinning the
  default asyncio event loop policy. No other global fixtures exist — most tests construct their
  fixtures (a fresh `PriceCache()`, a fresh `SimulatorDataSource(...)`) inline at the top of the
  test body rather than via `@pytest.fixture`, which keeps each test's setup visible in the test
  itself. `pytest.fixture` is used sparingly, only for genuinely shared/parametrized setup (see
  Mocking below).

**Run commands** (always via `uv`, never bare `python`/`pytest`):
```bash
uv run --extra dev pytest -v                 # All tests, verbose
uv run --extra dev pytest --cov=app          # With coverage
uv run --extra dev pytest tests/market/test_cache.py   # Single file
uv run --extra dev ruff check app/ tests/    # Lint (run alongside tests)
```

## Test File Organization

**Location:** Fully separate from source — `backend/tests/` mirrors `backend/app/` by subsystem
(`backend/tests/market/` for `backend/app/market/`). Not co-located with source files.

**Naming:** One test file per source module, exact name match:
`app/market/cache.py` → `tests/market/test_cache.py`
`app/market/models.py` → `tests/market/test_models.py`
`app/market/simulator.py` → `tests/market/test_simulator.py` (pure `GBMSimulator` math)
`app/market/stream.py` → `tests/market/test_stream.py`
`app/market/tickers.py` → `tests/market/test_tickers.py`
`app/market/massive_client.py` → `tests/market/test_massive.py`
`app/market/factory.py` → `tests/market/test_factory.py`

**Cross-cutting exception:** when multiple implementations share an interface (`MarketDataSource`),
add one extra file testing the *interface contract* against every implementation via
parametrization, named for the contract rather than either implementation:
`tests/market/test_conformance.py`. Also `test_simulator_source.py` exists alongside
`test_simulator.py` — the pure-math class (`GBMSimulator`) and its async wrapper
(`SimulatorDataSource`) get separate test files even though they live in the same source module,
because they test different concerns (deterministic math vs. asyncio task lifecycle).

**Structure:**
```
backend/tests/
├── __init__.py
├── conftest.py              # one shared fixture: event_loop_policy
└── market/
    ├── __init__.py
    ├── test_cache.py         # PriceCache + wait_for_price
    ├── test_conformance.py   # MarketDataSource contract, both implementations
    ├── test_factory.py       # create_market_data_source() env-var branching
    ├── test_massive.py       # MassiveDataSource, REST client mocked
    ├── test_models.py        # PriceUpdate derived properties
    ├── test_simulator.py     # GBMSimulator pure math
    ├── test_simulator_source.py  # SimulatorDataSource asyncio wrapper
    ├── test_stream.py        # SSE generator, driven directly (no ASGI server)
    └── test_tickers.py       # normalize_ticker validation
```

## Test Structure

**Suite organization** — one `Test<UnitUnderTest>` class per unit, methods grouped by concern
with a `# --- Section ---` comment divider inside the class where the unit has multiple facets:

```python
class TestPriceCache:
    """Unit tests for the PriceCache."""

    def test_update_and_get(self):
        """Test updating and getting a price."""
        cache = PriceCache()
        update = cache.update("AAPL", 190.50)
        assert update.ticker == "AAPL"
        assert update.price == 190.50
        assert cache.get("AAPL") == update

    # --- Session baseline ---

    def test_first_update_pins_the_session_baseline(self):
        """The first update for a ticker sets its open_price."""
        ...

    # --- History ---

    def test_history_is_bounded_and_ordered(self):
        ...

    # --- Health ---

    def test_newest_timestamp_empty_cache(self):
        ...
```
(`backend/tests/market/test_cache.py`)

**Naming:** test method names are full sentences describing the behavior under test —
`test_open_price_survives_later_updates`, `test_repeated_price_does_not_bump_version`,
`test_stops_when_client_disconnects_immediately` — not `test_1` or `test_update`. Every test has
a one-line docstring restating the behavior in plain English, even when the name is already
fairly clear.

**Setup/teardown:** no `setUp`/`tearDown`, no class-level fixtures for simple units — each test
builds a fresh instance (`cache = PriceCache()`) as its first line. For async lifecycle objects
that need cleanup, `stop()` (or equivalent) is called explicitly at the end of the test body
rather than via a fixture teardown, keeping the full lifecycle visible in one test:

```python
async def test_remove_ticker_clears_the_cache(self, source_and_cache):
    source, cache = source_and_cache
    await source.start(["AAPL", "GOOGL"])
    await source.remove_ticker("AAPL")
    assert "AAPL" not in cache
    assert "AAPL" not in source.get_tickers()
    await source.stop()
```

**Assertion style:** plain `assert` statements (pytest's assertion rewriting), no custom assertion
helpers. `pytest.approx(x, abs=1e-3)` for floating-point comparisons involving derived percentages
(GBM outputs, percent-change calculations). `pytest.raises(ValueError, match="...")` for expected
validation failures, matching on a substring of the user-facing message.

## Mocking

**Framework:** `unittest.mock` (`AsyncMock`, `MagicMock`, `patch`) — no `pytest-mock` or other
mocking library added.

**Pattern — parametrized fixture standing up both implementations of an interface**, with the
mock scoped only to the implementation that needs external I/O stubbed:

```python
def _snapshot(ticker: str, price: float) -> MagicMock:
    snap = MagicMock()
    snap.ticker = ticker
    snap.last_trade = MagicMock(price=price, timestamp=1605195918306274000)
    snap.min = None
    snap.day = None
    return snap


@pytest.fixture(params=["simulator", "massive"])
def source_and_cache(request):
    cache = PriceCache()
    if request.param == "simulator":
        yield SimulatorDataSource(cache, update_interval=0.05), cache
    else:
        source = MassiveDataSource(
            "test-key", cache, poll_interval=60.0, backfill_history=False
        )
        with (
            patch.object(source, "_fetch_snapshots", return_value=[...]),
            patch.object(source, "_log_market_status", new=AsyncMock()),
            patch("app.market.massive_client.RESTClient"),
        ):
            yield source, cache
```
(`backend/tests/market/test_conformance.py`)

**What to mock:** only the actual external boundary — the third-party REST client
(`RESTClient` from the `massive` package) and network-bound async helper methods
(`_fetch_snapshots`, `_log_market_status`). Everything internal (the cache, the ticker
validation, the GBM math) runs for real.

**What NOT to mock:** the unit under test's own logic. `PriceCache`, `GBMSimulator`, and the SSE
generator are exercised directly with real objects and real (small/tunable) timing parameters —
never mocked out. The simulator's asyncio task is tested with a very short `update_interval`
(e.g. `0.05`), not by mocking `asyncio.sleep`.

**Driving async generators/handlers directly, without an ASGI server:** the SSE endpoint is
tested by calling the internal `_generate_events()` async generator directly with a stub
`Request`-like object, rather than spinning up FastAPI's TestClient:

```python
class _StubRequest:
    """Minimal stand-in for a FastAPI Request, driving disconnect after N checks."""

    client = None

    def __init__(self, disconnect_after: int):
        self._calls = 0
        self._limit = disconnect_after

    async def is_disconnected(self) -> bool:
        self._calls += 1
        return self._calls > self._limit
```
Frames are collected with `[f async for f in _generate_events(cache, _StubRequest(3), interval=0.0)]`.
Use this pattern for any future SSE/streaming or long-lived generator logic: extract the
generator as a plain (testable) function separate from the router closure that wires it to
`StreamingResponse`, and give it `interval`/`heartbeat` parameters that tests can zero out.

## Fixtures and Factories

No shared fixture/factory module exists yet (e.g. no `tests/factories.py`). Test data is built
inline per test, using constants close to the plan's example values (`"AAPL"`, `190.50`) so
assertions read naturally against the spec. If a future phase needs shared fixtures (e.g. a seeded
test database), add a `conftest.py` at the relevant test subdirectory level (`tests/portfolio/`,
`tests/chat/`) following the existing package-per-subsystem test layout, keeping fixtures scoped
to the subsystem that needs them rather than adding everything to the root `conftest.py`.

## Coverage

**Configuration:** `[tool.coverage.run]` sources `app`, omits `tests/*`. Standard
`exclude_lines` in `[tool.coverage.report]` (`pragma: no cover`, `__repr__`, `NotImplementedError`,
`if __name__ == "__main__":`, `if TYPE_CHECKING:`).

**Requirement:** no numeric coverage threshold enforced in config — coverage is measured and
reported, not gated. In practice the market module has near-total behavioral coverage: every
public method of `PriceCache`, every abstract method of `MarketDataSource` (via the conformance
suite), every property of `PriceUpdate`, and every branch of the SSE generator has a dedicated
test.

**View coverage:**
```bash
uv run --extra dev pytest --cov=app --cov-report=term-missing
```

## Test Types

**Unit tests:** the entire existing suite is unit-level — no integration tests against a real
FastAPI `TestClient`/HTTP layer exist yet, and no database exists yet (see PLAN.md build order:
step 2 introduces the database). When those land, follow the same one-file-per-module,
`Test<Unit>` class convention.

**Interface conformance tests:** a distinct category from ordinary unit tests — see
`test_conformance.py` above. Use this pattern for any interface with 2+ implementations
(e.g. mock LLM vs. real LLM client, if that ever needs an abstraction).

**Integration tests:** none yet in `backend/tests/`. PLAN.md section 12 specifies these will be
FastAPI route tests once portfolio/watchlist/chat routers exist ("API routes: correct status
codes, response shapes, error handling").

**E2E tests:** none in the backend suite — PLAN.md section 12 specifies Playwright E2E tests will
live in a separate top-level `test/` directory, run on the host against the running Docker
container, not part of the `uv run pytest` suite. Not yet present in the repo.

## Common Patterns

**Async testing** (class-level marker + async `def test_*` methods):
```python
@pytest.mark.asyncio
class TestWaitForPrice:
    """Unit tests for the wait_for_price helper."""

    async def test_waits_for_a_price_that_arrives_late(self):
        cache = PriceCache()

        async def seed_later():
            await asyncio.sleep(0.05)
            cache.update("AAPL", 190.00)

        task = asyncio.create_task(seed_later())
        price = await wait_for_price(cache, "AAPL", timeout=1.0)
        assert price == 190.00
        await task
```
(`backend/tests/market/test_cache.py`)

**Error testing:**
```python
async def test_raises_on_timeout(self):
    cache = PriceCache()
    with pytest.raises(ValueError, match="AAPL"):
        await wait_for_price(cache, "AAPL", timeout=0.1)
```
`match=` asserts on a fragment of the user-facing message, tying the test back to the actual text
a user would see, not just the exception type.

**Testing deterministic behavior that is nominally random:** for GBM/hash-derived values
(`synthesize_params`), tests assert determinism (same input → same output across calls) and
range bounds, rather than exact values — since the underlying generator is intentionally
randomized (GBM) or hash-derived (synthesized ticker params).

**Avoid real sleeps for timing logic:** tests that exercise time-based behavior use `timestamp=`
parameters passed explicitly into `cache.update(..., timestamp=100.0)` rather than
`time.sleep()`, or use tunable `interval=0.0`/`update_interval=0.05` constructor parameters so
the test suite runs fast and deterministically.

---

*Testing analysis: 2026-08-04*
