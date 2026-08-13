---
phase: 3
slug: portfolio-watchlist-apis
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-12
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8.3.0 with pytest-asyncio 1.3.0 |
| **Config file** | `backend/pyproject.toml` → `[tool.pytest.ini_options]` (`testpaths = ["tests"]`, `asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "function"`) |
| **Quick run command** | `cd backend && uv run --extra dev pytest tests/services tests/api -q` |
| **Full suite command** | `cd backend && uv run --extra dev pytest -q` |
| **Lint gate** | `cd backend && uv run --extra dev ruff check app/ tests/` |
| **Estimated runtime** | ~30 seconds full suite (baseline: 243 tests collected) |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && uv run --extra dev pytest tests/services tests/api -q` plus `uv run --extra dev ruff check app/ tests/`
- **After every plan wave:** Run `cd backend && uv run --extra dev pytest -q` — must be **>= 243 + new tests passing**, allowing at most the one known `tests/market/test_simulator_source.py::test_custom_update_interval` flake
- **Before `/gsd-verify-work`:** Full suite green (one retry of the known flake permitted)
- **Max feedback latency:** 30 seconds

**Rationale for the rate:** the trade path is a read-modify-write on money with six independent rejection branches. Anything less than running the whole `tests/services` package per commit lets a rounding or ordering regression in one branch hide behind a passing sibling.

---

## Per-Task Verification Map

| Req ID | Behavior | Test Type | Automated Command | File Exists | Status |
|--------|----------|-----------|-------------------|-------------|--------|
| PORT-01 | Portfolio read: cash, total, per-position figures | unit + route | `pytest tests/services/test_portfolio.py tests/api/test_portfolio.py -q` | ❌ W0 | ⬜ pending |
| PORT-02 | Buy decreases cash by fill amount | service | `pytest tests/services/test_trading.py -q` | ❌ W0 | ⬜ pending |
| PORT-03 | Sell increases cash by fill amount | service | `pytest tests/services/test_trading.py -k sell -q` | ❌ W0 | ⬜ pending |
| PORT-04 | Buy over cash → 400 + message naming need/have | service + route | `pytest tests/services/test_trading.py tests/api/test_portfolio.py -q` | ❌ W0 | ⬜ pending |
| PORT-05 | Sell over shares held → 400 | service | `pytest tests/services/test_trading.py -q` | ❌ W0 | ⬜ pending |
| PORT-06 | 0 / negative / NaN / Infinity / >4dp → 400 | unit (parametrized) | `pytest tests/services/test_trading.py -k quantity -q` | ❌ W0 | ⬜ pending |
| PORT-07 | Unwatched ticker auto-added by the trade | service | `pytest tests/services/test_trading.py -q` | ❌ W0 | ⬜ pending |
| PORT-08 | 2s wait on a priceless ticker, then fill | service (fake cache populated on a timer) | `pytest tests/services/test_trading.py -k wait -q` | ❌ W0 | ⬜ pending |
| PORT-09 | Sell to zero deletes the row | service | `pytest tests/services/test_trading.py -q` | ❌ W0 | ⬜ pending |
| PORT-10 | Response carries the server-side `fill_price` | route | `pytest tests/api/test_portfolio.py -q` | ❌ W0 | ⬜ pending |
| PORT-11 | Every trade writes a snapshot | service | `pytest tests/services/test_trading.py -q` | ❌ W0 | ⬜ pending |
| PORT-12 | 30s task writes on change, skips on no-change | unit (call the loop body directly, not the sleep) | `pytest tests/services/test_snapshots.py -q` | ❌ W0 | ⬜ pending |
| PORT-13 | `?limit=` and `?since=` | route | `pytest tests/api/test_portfolio.py -q` | ❌ W0 | ⬜ pending |
| PORT-14 | Reset → $10k, no positions, watchlist untouched | service + route | `pytest tests/services/test_portfolio.py -k reset -q` | ❌ W0 | ⬜ pending |
| WATCH-01 | Price, open, change-from-open, ~60 history points | route | `pytest tests/api/test_watchlist.py -k read -q` | ❌ W0 | ⬜ pending |
| WATCH-02 | Invalid symbol → 400 | route | `pytest tests/api/test_watchlist.py -q` | ❌ W0 | ⬜ pending |
| WATCH-03 | Add registers with the live source | service (fake source recording calls) | `pytest tests/services/test_watchlist.py -q` | ❌ W0 | ⬜ pending |
| WATCH-04 | Remove an unheld ticker succeeds | route | `pytest tests/api/test_watchlist.py -k remove -q` | ❌ W0 | ⬜ pending |
| WATCH-05 | Remove a held ticker → 409, readable message | service + route | `pytest tests/services/test_watchlist.py tests/api/test_watchlist.py -q` | ❌ W0 | ⬜ pending |
| WATCH-06 | Remove an unwatched ticker → 404 | route | `pytest tests/api/test_watchlist.py -q` | ❌ W0 | ⬜ pending |
| TEST-02 | Aggregate: trade execution + every rejection path | suite | `pytest tests/services -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**On the `-k` selectors.** Only six survive: `-k sell`, `-k quantity`, `-k wait`, `-k reset`,
`-k read` and `-k remove` — each matches a **class name** an owning plan pins verbatim
(`TestSell`, `TestQuantityValidation`, `TestPriceWait`, `TestResetPortfolio`, `TestReadWatchlist`,
`TestRemoveTicker`), and `-k` matching is case-insensitive substring matching, so the class name is
enough. Every other selector this map originally carried — `insufficient_cash`,
`insufficient_shares`, `auto_add`, `delete_at_zero`, `register`, `not_found`, `conflict`,
`fill_price`, `history`, `invalid`, `buy`, `snapshot` — depended on underscore-separated *function*
names that no plan pins, and an underscored selector does not match a CamelCase class name. A
selector matching zero tests makes pytest **exit 5**, which post-execution validation reads as red.
Those rows are relaxed to file-level runs rather than pinning function names across five plans; the
per-requirement behavior each row names is still asserted, it is simply asserted by a file rather
than isolated by a selector.

---

## Wave 0 Requirements

- [ ] `backend/app/services/__init__.py` — package does not exist (directory is empty)
- [ ] `backend/tests/services/__init__.py` — test package does not exist (directory is empty)
- [ ] `backend/tests/services/test_trading.py` — covers PORT-02..PORT-11, TEST-02
- [ ] `backend/tests/services/test_portfolio.py` — covers PORT-01, PORT-14
- [ ] `backend/tests/services/test_watchlist.py` — covers WATCH-03, WATCH-05
- [ ] `backend/tests/services/test_snapshots.py` — covers PORT-12
- [ ] `backend/tests/api/test_portfolio.py` — covers PORT-01, PORT-10, PORT-13, status codes
- [ ] `backend/tests/api/test_watchlist.py` — covers WATCH-01, WATCH-02, WATCH-04, WATCH-05, WATCH-06
- [ ] `backend/tests/services/conftest.py` — shared fixture for a fake `MarketDataSource` recording `add_ticker`/`remove_ticker` calls (needed because `SimulatorDataSource.add_ticker` no-ops before `start()`). Scoped to `tests/services/` so Phase 1's root fixtures stay untouched
- [ ] Framework install: **none required** — pytest, pytest-asyncio, httpx and ruff are already in the `dev` extra

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live valuation against a real streaming simulator over minutes | PORT-01 | Automated tests use a fixed fake cache; drift over a long-running stream is only observable live | Start the container, hold a position, watch the portfolio total move with the ticker |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
