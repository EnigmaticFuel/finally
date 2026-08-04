# FinAlly E2E tests

Playwright, run on the host against the container. No test compose file and no
second container: browser dependencies stay out of the production image.

## Running

```bash
cd test
npm install
npx playwright install chromium
npx playwright test
```

`global-setup.ts` removes the container, deletes `db/finally.db`, and starts the
app again with `scripts/start_windows.ps1`, so every run begins from a freshly
seeded $10,000 database. Point the suite elsewhere with `FINALLY_URL`.

## Prerequisites

- Docker Desktop running.
- `LLM_MOCK=true` in the project root `.env`. The chat tests assert against the
  frozen mock contract in PLAN.md section 9, so global setup refuses to run
  without it rather than quietly billing a real model.

## Layout

| File | Covers |
|---|---|
| `specs/01-fresh-start.spec.ts` | Default watchlist, seed balance, streaming prices, sparklines on first paint |
| `specs/02-watchlist.spec.ts` | Add, remove, invalid symbol, removal blocked by an open position |
| `specs/03-trading.spec.ts` | Buy, sell, sell to zero, fill price, insufficient cash and shares |
| `specs/04-visualization.spec.ts` | Heatmap cells and colours, P&L chart, main chart |
| `specs/05-chat.spec.ts` | Every mock keyword branch, inline actions, reload persistence |
| `specs/06-sse-resilience.spec.ts` | Stream blocked with `page.route`, status dot, recovery |

Tests run serially in one worker: they share one SQLite database in one
container, so parallel workers would trade against each other's cash. Each file
restores the default portfolio shape afterwards, and only the fresh start file
asserts absolute money figures.

## Conventions

- Wait on state, never on the clock. Prices tick every 500ms; assertions poll
  for a value to change rather than sleeping.
- Assert on stable things. A position existing or cash having decreased is
  stable; an exact live price is not.
- Selectors are the `data-testid` attributes the frontend exposes.
