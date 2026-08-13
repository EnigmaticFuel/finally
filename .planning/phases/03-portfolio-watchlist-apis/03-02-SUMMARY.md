---
phase: 03-portfolio-watchlist-apis
plan: 02
subsystem: backend-services
status: complete
tags: [trading, sell, validation, rejection-suite, tdd, sqlite]

requires:
  - "03-01 — execute_trade, _apply_trade, TradeError, the writing() unit of work"
  - "backend/app/db/ (Phase 1) — delete_position, is_zero, upsert_position, update_cash_balance"
  - "backend/app/market/ (frozen) — PriceCache, wait_for_price"
provides:
  - "The sell settlement arm: cash credited, shares debited, row deleted at zero"
  - "The insufficient-shares guard — the 'no shorting' promise enforced rather than asserted"
  - "TEST-02's rejection suite for the trade path (31 tests in test_trading.py)"
affects:
  - "03-05 (full-suite gate in wave 3)"
  - "Phase 4 (fill receipt reads total_cost, which carries proceeds on a sell)"
  - "Phase 6 (LLM trades route through the same guards)"

tech-stack:
  added: []
  patterns:
    - "Two-armed branch on side inside one writing() block; one shared update_cash_balance below it"
    - "is_zero for share remainders, never a bare float equality"
    - "Every rejection test matches on its own branch's message, never on the exception type"

key-files:
  created: []
  modified:
    - backend/app/services/trading.py
    - backend/tests/services/test_trading.py

decisions:
  - "Sell proceeds report in total_cost — TradeResponse declares one field, no side-specific variant"
  - "Share figures format with :g so a whole-share quantity prints no trailing decimal zero"
  - "The fill_price precision criterion was rewritten: PriceCache rounds to cents upstream, so the service's non-rounding is proven on total_cost instead"

metrics:
  duration: "~25 min"
  completed: 2026-08-13
  tasks: 3
  commits: 4

actuals:
  tokens: 4600
  tasks: 3
  commits: 4

requirements: [PORT-03, PORT-04, PORT-05, PORT-06, PORT-08, PORT-09, TEST-02]
---

# Phase 3 Plan 02: Sell Settlement and the Rejection Suite Summary

The trade surface now says no as reliably as it says yes: sells settle cash and shares
through 03-01's single transaction, a sell to zero removes the position row entirely, and
every rejection branch is pinned by a test asserting that branch's own wording.

## What Was Built

**The sell arm (`backend/app/services/trading.py`).** The one stub line 03-01 pinned at
`trading.py:158` is replaced by the settlement branch, sitting exactly where the buy cash
guard sits. `held` is read from the position row inside the same `BEGIN IMMEDIATE` as the
write, so there is no read-then-write window an implicit short could open through.
`remaining = held - quantity` raises when `remaining < 0 and not is_zero(remaining)`, then
`delete_position` fires when `is_zero(remaining)` and `upsert_position` otherwise, carrying
`avg_cost` through unchanged (D-05).

The transaction's shape is untouched: still one `with writing(conn):` block, still one
`run_db` call, still `add_watchlist_ticker` first and unconditional, still the shared tail of
`insert_trade` / `get_positions` / `value_portfolio` / `insert_snapshot`. The only structural
move is `update_cash_balance(conn, new_cash)` dropping below the branch so it is called once
for both sides rather than once per arm — both arms now set a single `new_cash` local.
`execute_trade`'s signature is byte-identical, verified by `inspect.signature`.

**The rejection suite (`backend/tests/services/test_trading.py`).** 31 tests, up from 3.
`TestSell` covers partial and full sells, the oversell refusal with the database asserted
unmoved, an unheld ticker reporting zero held, both 4dp boundaries, and three fractional
sells summing to the holding that still delete the row. `TestQuantityValidation` parametrizes
8 rejected values, each with its own `match=`. `TestInsufficientCash` asserts both sides of
the cash boundary. `TestPriceWait` proves the two-second window in both directions and proves
validation runs ahead of it.

## Key Decisions

**Share figures format with `:g`.** The refusal reads `Insufficient shares: need 11 PYPL,
have 10` — no trailing decimal zero on a whole-share figure, as the plan requires, and no
helper function added (this plan was scoped to create no new symbol under `app/`).

**`is_zero`, never an equality.** Selling 0.3, then 0.1, then 0.2 out of 0.6 leaves residue on
the order of 1e-17. An equality test against zero would strand a dust holding the user can
never sell and the P&L chart can never value. The test drives exactly that sequence.

**Tasks 2 and 3 had no RED phase, and that is correct.** Task 1 was a genuine RED/GREEN cycle:
9 tests failed against the pinned stub, then passed against the sell arm. Tasks 2 and 3 are
characterization tests over behavior 03-01 and Task 1 already shipped — `validate_quantity`'s
three branches and the cash guard existed and were correct. Writing a deliberately failing
version first would have proven nothing. The plan itself frames Task 2 as "test authoring
plus, at most, correcting a check order," so this is the planned shape rather than a skipped
gate. Both are committed under `test(...)`.

**`validate_quantity`'s check order needed no correction.** The plan instructed correcting it
if it was anything other than finiteness, then positivity, then precision. It already is
(`trading.py:77-83`), so nothing changed. The order is now pinned by a test asserting `inf`
and `nan` share the finiteness wording and that `1e-9` reports the precision wording instead —
the two branches cannot be proven by one another.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] A test asserted no comma anywhere in the refusal message**

- **Found during:** Task 2 verification
- **Issue:** The plan requires the cash figures carry no thousands separator. My first
  assertion was `"," not in message`, which failed against
  `Insufficient cash: need $10000.01, have $10000.00` — PLAN.md section 8's own message shape
  puts a comma between the two clauses. The test was wrong, not the code.
- **Fix:** narrowed the assertion to `f"{STARTING_CASH:,.2f}" not in message`, which tests the
  actual requirement — no separator inside a figure — rather than the punctuation of the
  sentence.
- **Files modified:** `backend/tests/services/test_trading.py`
- **Commit:** 1645d56

**2. [Rule 1 - Bug] An acceptance criterion was unsatisfiable as literally written**

- **Found during:** Task 3 verification
- **Issue:** The criterion "A test asserts the returned `fill_price` equals a seeded price
  carrying more than two decimal places, unrounded" cannot hold. Root cause, proven before
  changing anything: `PriceCache.update` rounds every price to cents as it stores it
  (`backend/app/market/cache.py:48`, `price = round(price, 2)`). Seeding 190.123456 and
  reading back gives 190.12. The rounding belongs to the frozen market module, upstream of
  this seam — the service adds none of its own.
- **Fix:** rewrote the test to pin what the criterion protects. It asserts `fill_price` equals
  `cache.get_price(...)` exactly (the float `wait_for_price` returned, passed through
  untouched) and that `total_cost` equals the raw product. The quantity is 0.3333 so the
  product is 63.366996 — genuinely sub-cent, so the assertion would fail if the service
  applied `round_money` to the stored figure. An earlier draft used quantity 3.0, but
  `190.12 * 3.0` is exactly 570.36 and would have discriminated nothing; that was checked
  numerically rather than assumed.
- **Files modified:** `backend/tests/services/test_trading.py`
- **Commit:** b514799

**3. [Rule 3 - Blocking] `uv` cannot hardlink into the OneDrive-backed worktree**

- **Found during:** Task 1 verification
- **Issue:** the known `os error 396` this repo already carries, recorded in 03-01's summary
  and in the orchestrator's brief.
- **Fix:** every `uv` command run with `UV_LINK_MODE=copy`. Environment-only; nothing added to
  the repo.
- **Files modified:** none

### Environment Observation (no action taken)

Every `git commit` in this worktree printed
`error: failed to delete '.git/worktrees/agent-a3cac8aca70d5c526': Permission denied` to
stderr while still committing successfully. This is git's auto-gc attempting to prune a
sibling wave-2 worktree's admin directory and being refused by Windows because that worktree
is live. The failure is the safe outcome — the sibling agent's worktree is intact — and every
commit hash was verified in `git log` afterwards. No workaround applied; nothing to fix.

## Verification

| Check | Result |
|---|---|
| `pytest tests/services/test_trading.py -q` | 31 passed |
| `pytest tests/services tests/api -q` (plan gate) | 40 passed |
| `pytest tests/services/test_trading.py -k quantity -q` | 10 passed (criterion: at least 6) |
| `pytest tests/services/test_trading.py -k wait -q` | 4 passed |
| `ruff check app/ tests/` | All checks passed |
| `grep -c "with writing(conn):" app/services/trading.py` | 1 |
| `grep -c "update_cash_balance(conn" app/services/trading.py` | 1 |
| SQL grep over `trading.py` | 0 |
| `inspect.signature(execute_trade)` | `['db_path', 'cache', 'ticker', 'side', 'quantity']` |
| `validate_quantity(0.0001)` | `0.0001` |
| `git status --porcelain -- db/finally.db` | no output |
| `git status --porcelain` over all frozen and other-plan paths | no output |

The full suite was deliberately not run: three wave-2 plans share this tree, and a full
`pytest -q` here would collect a sibling's half-written module and report a red belonging to
nobody. The `>= 243 + new` full-suite gate is 03-05 Task 4's, in wave 3.

## Files Touched

Exactly the two this plan declares. `app/services/__init__.py`, `app/api/models.py`,
`app/db/`, `app/market/`, `app/main.py` and the two sibling service modules are all
unmodified — confirmed by `git status --porcelain` over each path.

## Known Stubs

None. The one stub this plan inherited — 03-01's
`raise TradeError("Sell orders are not yet wired up")` — is the line this plan replaced, and
it is gone. No placeholder text, no unwired branch, no hardcoded empty value reaching a
response.

## Flagged Assumptions Resolved As Planned

Both `unclassified` probe rows came out as the planner read them, and both are now proven in
behavior rather than assumed:

- **PORT-05.** *Shares held* is the `quantity` on the row read inside the same
  `BEGIN IMMEDIATE` as the write. A ticker with no row counts as zero held, so selling one is
  a 400 "insufficient shares" and not a 404 —
  `test_selling_an_unheld_ticker_reports_zero_held` asserts the message reads `have 0`. The
  rejection fires before any cash is credited, and
  `test_oversell_is_refused_and_the_database_is_unmoved` asserts cash, the position, the
  trades log and the snapshot count are all unmoved.
- **PORT-09.** *Takes to zero* is decided by `is_zero(remaining)` against the existing 1e-6
  epsilon, so residue from repeated fractional sells still deletes the row. *Deletes entirely*
  means no row survives — `get_position` returns `None`, asserted directly. The consequence a
  reviewer should check is confirmed by
  `test_full_sell_snapshot_values_the_portfolio_as_cash_alone`: the trade's own snapshot,
  written after the delete, values the portfolio at cash alone.

## Threat Flags

No new security-relevant surface beyond the plan's `<threat_model>`. This plan added no
endpoint, no input path and no dependency. T-03-02-01 through T-03-02-05 and T-03-02-07 all
have their mitigations present and tested: the holding is read inside the write transaction,
only `delete_position` or a strictly positive `upsert_position` can run, finiteness is checked
first, every rejection raises before `insert_trade` and inside `writing()`, and the messages
carry only tickers, quantities and two-decimal cash figures.

## Self-Check: PASSED

Both modified files verified present on disk with the expected content: `trading.py` contains
`delete_position(` and `is_zero(`, `test_trading.py` contains `class TestSell`. All four
commits verified in `git log`: `1be5b70`, `63b9572`, `1645d56`, `b514799`.
