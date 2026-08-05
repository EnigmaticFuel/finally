# Stack Research

**Domain:** Single-container real-time trading workstation (FastAPI + static Next.js + SQLite + SSE + LLM copilot)
**Researched:** 2026-08-05
**Confidence:** HIGH

> **Scope.** This covers only what must be **added** on top of the frozen market data subsystem. `backend/app/market/` (FastAPI >=0.115, uvicorn[standard] >=0.32, numpy >=2.0, massive==2.2.0, rich, pytest/pytest-asyncio/pytest-cov, ruff, hatchling, Python >=3.12) is a fixed constraint, not a subject of research. Every version below was verified against a **live registry or the shipped package artifact** on 2026-08-05, not from training data.

---

## Executive Summary — the five things that will bite

Four of the nine questions have answers that differ from the plan or from what a 2025-trained agent would assume. Read these before anything else.

| # | Finding | Impact |
|---|---------|--------|
| 1 | **Node 24 is Active LTS. Node 22 went to Maintenance on 2025-10-21.** PLAN.md section 11 says Node 22. | Change the Dockerfile build stage to `node:24-slim`. Low risk, one line. |
| 2 | **TypeScript 7.0.2 is `latest` on npm and it will break Next.js.** TS 7 is the Go rewrite; it dropped `lib/typescript.js` (the JS Compiler API) which Next.js integrates through. | **Pin `typescript@^5`.** `create-next-app@16.3.0` itself still scaffolds `"typescript": "^5"`. Never run `npm install typescript@latest`. |
| 3 | **OpenRouter provider routing can silently degrade structured outputs.** With `{"provider":{"order":["cerebras"]}}` alone, `allow_fallbacks` defaults to `true`. Three live endpoints for this model (DigitalOcean, SambaNova, Amazon Bedrock) report `response_format: false`. | If Cerebras is saturated the request falls through to a provider that **ignores `response_format`** and returns prose. `model_validate_json` then throws on a chat message. **Must set `allow_fallbacks: false`.** |
| 4 | **Tailwind v4 has no `tailwind.config.js`.** Config is CSS-first via `@import "tailwindcss"` + `@theme`. | Any agent writing a `tailwind.config.ts` with a `content: []` array is working from stale training data and will produce a build that emits no utilities. |
| 5 | **Recharts 3 Treemap is confirmed present and typed** — the one-library bet in PLAN.md section 10 holds. | Verified by extracting `types/chart/Treemap.d.ts` from the `recharts@3.10.1` tarball. No second charting library needed. |

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **Next.js** | `16.3.0` | Frontend framework, built as static export | Current `latest` dist-tag. `output: 'export'` is a first-class, documented mode. Engines `node>=20.9.0`, peer `react ^19`. |
| **React / React DOM** | `19.2.8` | UI runtime | Required by Next 16. Every other frontend lib below declares React 19 peer support. |
| **TypeScript** | `^5` (→ `5.9.3`) | Types | **Not 7.x.** See finding #2. Matches Vercel's own scaffold pin. |
| **Tailwind CSS** | `4.3.3` | Styling | Current major. CSS-first config; `@theme` maps design tokens to utilities in one step, which suits the fixed FinAlly palette. |
| **Recharts** | `3.10.1` | All four chart types incl. Treemap | Only mainstream React chart lib with line + sparkline + treemap in one bundle. v2 is explicitly EOL upstream. |
| **LiteLLM** | `1.95.0` | LLM gateway → OpenRouter → Cerebras | Mandated by `cerebras` skill + PLAN.md §9. `openrouter/openai/gpt-oss-120b` carries `supports_response_schema: true` in current metadata. |
| **Pydantic** | `2.13.4` | Structured-output schema + API models | Already a transitive FastAPI dep; `response_format=<BaseModel>` is the LiteLLM structured-output path. |
| **stdlib `sqlite3`** | Python 3.12 builtin | Persistence | **No aiosqlite, no ORM.** See the SQLite section — the correct answer is `def` endpoints, not async. |
| **Node.js** | `24.x` (Krypton) | Docker build stage | Active LTS. Supersedes PLAN.md's Node 22. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `@tailwindcss/postcss` | `4.3.3` | Tailwind v4 PostCSS plugin | Required — v4 no longer works via the `tailwindcss` PostCSS plugin directly |
| `postcss` | latest | Build pipeline | Peer of the above |
| `python-dotenv` | `1.2.2` | Load root `.env` from `backend/` | Backend must read `../.env` per PLAN.md §5 |
| `@playwright/test` | `1.62.1` | Host-run E2E | `test/` project only |
| `vitest` | `4.1.10` | Frontend unit tests | `frontend/` devDep |
| `@vitejs/plugin-react` | `6.0.5` | JSX transform for Vitest | Per Next.js official Vitest guide |
| `jsdom` | `30.0.1` | DOM environment | Vitest `environment: 'jsdom'` |
| `@testing-library/react` | `16.3.2` | Component tests | Peer allows `react ^19` — verified |
| `@testing-library/dom` | `^10` | Required peer of RTL 16 | Must be installed explicitly |
| `vite-tsconfig-paths` | `6.1.1` | Path alias resolution in tests | Only if using `@/*` aliases |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `uv` | Python deps | `uv add litellm pydantic python-dotenv` — `litellm` is currently loose in the venv and **absent from `uv.lock`**; this must be fixed |
| `ruff >=0.7.0` | Python lint | Already configured, `target-version = "py312"`, line-length 100 |
| `npm ci` | Frontend install | Requires `package-lock.json` committed |
| `pytest 9.x` | Backend tests | Existing pin is `>=8.3.0`; 9.1.1 is current and satisfies it. Verify the 154 existing tests still pass if you let it float |

---

## Installation

```bash
# --- frontend/ (run from frontend/) ---
npx create-next-app@16.3.0 . --ts --tailwind --app --no-src-dir --import-alias "@/*"

npm install recharts@3.10.1
npm install -D vitest@4 @vitejs/plugin-react jsdom \
              @testing-library/react @testing-library/dom @testing-library/jest-dom \
              vite-tsconfig-paths

# Guard rail: never let TypeScript float to 7.x
npm pkg set devDependencies.typescript="^5"
npm install

# --- backend/ (run from backend/) ---
uv add litellm pydantic python-dotenv
# sqlite3 is stdlib - nothing to install

# --- test/ (host-run Playwright, run from test/) ---
npm install -D @playwright/test@1.62.1
npx playwright install --with-deps chromium
```

---

## 1. Next.js Static Export

**Verified against** `https://nextjs.org/docs/app/guides/static-exports` — page metadata reports `version: 16.3.0`, `lastUpdated: 2026-07-21`. **Confidence: HIGH.**

### `next.config.ts`

```ts
import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  output: 'export',

  // Emits /me/index.html instead of /me.html.
  // Required for FastAPI StaticFiles(html=True) to resolve nested routes,
  // because Starlette looks for <path>/index.html on a directory request
  // and will NOT try <path>.html.
  trailingSlash: true,

  // Static export has no image optimization server. Without this,
  // next/image throws at build time.
  images: { unoptimized: true },
}

export default nextConfig
```

`next build` writes to `out/`. Docker stage 2 copies `out/` → `/app/static`.

### What breaks under static export

Directly from the "Unsupported Features" list:

| Unsupported | Relevance to FinAlly |
|-------------|----------------------|
| Route Handlers that rely on `Request` | **None** — every API is FastAPI. Do not create `app/api/**` at all. |
| Cookies / Draft Mode | None — no auth |
| `rewrites`, `redirects`, `headers` | **Relevant** — cannot proxy `/api/*` in dev. See dev-mode note below. |
| Proxy (middleware) | None |
| Server Actions | **Relevant** — trade submission must be `fetch()` from a Client Component |
| ISR | None |
| Image Optimization w/ default loader | Handled by `images.unoptimized` |
| Dynamic routes w/o `generateStaticParams` | None — single page app |

Two additional consequences that matter here:

- **Server Components still run — but only at build time.** A Server Component that fetches live prices would bake a build-time snapshot into HTML. Every FinAlly panel is live, so effectively **the entire app is `'use client'`**. Treat the root `page.tsx` as a thin Server Component shell that renders one client root.
- **`window`/`localStorage`/`EventSource` are unavailable during prerender.** Client Components *are* prerendered to HTML at build. All SSE wiring must live inside `useEffect`, never in a component body.

### Dev-mode gotcha (the one thing PLAN.md doesn't cover)

Because `rewrites` are unsupported, `next dev` on :3000 cannot proxy `/api/*` to FastAPI on :8000. Two options:

- **Recommended:** develop against the container. Run FastAPI on :8000 and point the frontend at it via `NEXT_PUBLIC_API_BASE` (empty string in production, `http://localhost:8000` in dev), with FastAPI CORS enabled **only** when a dev flag is set. One extra env var, no architecture change.
- Alternative: always `npm run build` and let FastAPI serve `out/`. Correct but a slow inner loop.

Either way, in production `NEXT_PUBLIC_API_BASE=''` keeps the single-origin/no-CORS property PLAN.md requires.

### Serving from FastAPI

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_market_feed()
    start_snapshot_task()
    yield
    await shutdown_tasks()

app = FastAPI(lifespan=lifespan)

app.include_router(portfolio_router)
app.include_router(watchlist_router)
app.include_router(chat_router)
app.include_router(health_router)
app.include_router(create_stream_router(price_cache))

# LAST. Always last.
app.mount("/", StaticFiles(directory="static", html=True), name="static")
```

`html=True` "automatically loads `index.html` for directories if such file exist" and "in HTML mode if `404.html` file exists it will be shown as 404 response" (Starlette docs). Next's export produces both `index.html` and `404.html`, so this pairs cleanly.

---

## 2. Recharts 3.10.1 — Treemap Confirmed

**Verified by extracting `recharts@3.10.1` from npm and reading `package/types/chart/Treemap.d.ts` and `package/types/index.d.ts` directly.** This is the shipped artifact, not documentation. **Confidence: HIGH.**

`recharts.org/en-US/api/Treemap` now 404s (docs moved to a Mintlify site), so the shipped `.d.ts` is the authority.

### Confirmed exports

```
export { Treemap } from './chart/Treemap';
export type { TreemapProps, TreemapNode, TreemapContentType } from './chart/Treemap';
export { LineChart } from './chart/LineChart';
export { AreaChart } from './chart/AreaChart';
export { ResponsiveContainer } from './component/ResponsiveContainer';
export { Tooltip } from './component/Tooltip';
```

### Treemap data shape (verbatim from the `.d.ts`)

```ts
export interface TreemapDataType {
    children?: ReadonlyArray<TreemapDataType>;
    [key: string]: unknown;
}
```

Flat array of objects; `children` makes it nested. FinAlly's heatmap is flat — one node per position.

### Props that matter (all quoted from the shipped types)

| Prop | Default | Note |
|------|---------|------|
| `data` | — | `ReadonlyArray<TreemapDataType>` |
| `dataKey` | `'value'` | "Decides how to extract the value" — string, number, or function |
| `nameKey` | `'name'` | "Name represents each sector in the tooltip" |
| `aspectRatio` | `1.618033988749895` | golden ratio |
| `type` | `'flat'` | `'flat'` renders all leaves; `'nest'` is click-to-zoom with breadcrumbs |
| `nodeGap` | `0` | **since 3.9** — spacing between siblings |
| `nodeInset` | `0` | **since 3.9** — insets children from parent bounds |
| `content` | — | `ReactNode \| ((props: TreemapNode) => React.ReactElement)` |
| `fill` / `stroke` / `colorPanel` | — | `colorPanel?: ReadonlyArray<string>` |
| `width` / `height` | — | `number \| Percent` — accepts `"100%"` |

### FinAlly heatmap usage

```tsx
import { Treemap, Tooltip, ResponsiveContainer } from 'recharts'

// value MUST be positive (it is the rectangle area).
// Size by market value; carry P&L separately for the fill color.
const data = positions.map(p => ({
  name: p.ticker,
  value: p.quantity * livePrice[p.ticker],   // area
  pnlPercent: p.unrealized_pnl_percent,      // color
}))

<ResponsiveContainer width="100%" height={260}>
  <Treemap
    data={data}
    dataKey="value"
    nameKey="name"
    type="flat"
    nodeGap={2}
    stroke="#30363d"
    isAnimationActive={false}
    content={<HeatCell />}
  >
    <Tooltip />
  </Treemap>
</ResponsiveContainer>
```

### Three Treemap pitfalls

1. **`content` must render SVG, not HTML.** The types say so verbatim: *"Use an SVG element or component, such as `<text>` or `<g>`. HTML elements such as `<div>` are not valid inside the chart SVG and may trigger React DOM warnings."* Ticker labels go in `<text>`, not `<div>`.
2. **Negative or zero `value` breaks layout.** P&L can be negative; market value cannot. Always size by market value and encode P&L in `fill`.
3. **Turn off animation for live data.** With a 500ms SSE cadence, `isAnimationActive` makes rectangles permanently in-flight. Set `false` on the Treemap and on the live line chart.

### Sparklines

No dedicated component — a `LineChart` with axes/tooltip/grid omitted, `dot={false}`, `isAnimationActive={false}`. ~60 points from `GET /api/watchlist`, extended client-side from SSE.

### React 19 compatibility — clear

Peer deps from the registry: `react: "^16.8.0 || ^17.0.0 || ^18.0.0 || ^19.0.0"`. **No React 19 issue.** Note `react-is` is a listed peer — npm auto-installs it, but if the lockfile is hand-edited it must not be dropped.

**Migration note:** v3 rewrote state management. `CategoricalChartState`, the `activeIndex` prop, and most internal cloned props were removed; `recharts-scale` and `react-smooth` are now vendored in. Any v2-era snippet an agent recalls may not compile. Build charts from the v3 types, not from memory.

---

## 3. Tailwind CSS 4.3.3 — CSS-First, No JS Config

**Verified against** `tailwindcss.com/docs/installation/framework-guides/nextjs` and `/docs/theme`. **Confidence: HIGH.**

```bash
npm install tailwindcss @tailwindcss/postcss postcss
```

**`postcss.config.mjs`** (verbatim from the framework guide):

```js
const config = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};
export default config;
```

**`app/globals.css`:**

```css
@import "tailwindcss";

@theme {
  /* FinAlly palette - PLAN.md section 2 */
  --color-accent:    #ecad0a;
  --color-primary:   #209dd7;
  --color-secondary: #753991;

  /* Terminal surfaces */
  --color-terminal-bg:    #0d1117;
  --color-terminal-panel: #161b22;
  --color-terminal-border:#30363d;

  /* Price direction */
  --color-uptick:   #26a69a;
  --color-downtick: #ef5350;

  --font-mono: "JetBrains Mono", ui-monospace, monospace;
}

/* Price flash - not a design token, so :root/plain CSS, not @theme */
@keyframes flash-up   { from { background-color: color-mix(in oklab, var(--color-uptick)   35%, transparent); } to { background-color: transparent; } }
@keyframes flash-down { from { background-color: color-mix(in oklab, var(--color-downtick) 35%, transparent); } to { background-color: transparent; } }

.flash-up   { animation: flash-up   500ms ease-out; }
.flash-down { animation: flash-down 500ms ease-out; }
```

`@theme` then yields `bg-terminal-bg`, `text-accent`, `border-terminal-border`, `font-mono` etc. automatically.

### The v4 rules an agent must internalize

| v3 (stale) | v4 (correct) |
|---|---|
| `tailwind.config.js` with `theme.extend` | `@theme { }` in CSS |
| `content: [...]` globs | Automatic source detection — no globs |
| `@tailwind base; @tailwind components; @tailwind utilities;` | `@import "tailwindcss";` (single line) |
| `tailwindcss` as the PostCSS plugin | `@tailwindcss/postcss` |
| `postcss-import` + `autoprefixer` needed | Both built in |

**`@theme` vs `:root`:** `@theme` generates CSS variables **and** utility classes; `:root` generates variables only. Put design tokens in `@theme`; put one-off animation variables in `:root`.

To wipe defaults and use only the FinAlly palette: `--color-*: initial;` as the first line inside `@theme`. Probably not wanted here — the default grays are useful for borders.

---

## 4. LiteLLM 1.95.0 → OpenRouter → Cerebras

**Confidence: HIGH** — verified against three independent live sources:
1. LiteLLM's own `model_prices_and_context_window.json` (main branch)
2. OpenRouter `GET /api/v1/models`
3. OpenRouter `GET /api/v1/models/openai/gpt-oss-120b/endpoints` (per-provider capability)

### Does structured output actually work? Yes — with one required guard.

Evidence:

```
# LiteLLM model metadata
openrouter/openai/gpt-oss-120b => {"provider":"openrouter","srs":true,"sfc":true,"mode":"chat"}
                                                            ^^^^^^^^^^ supports_response_schema
```

```
# OpenRouter model supported_parameters
[... "reasoning_effort", "response_format", "seed", "stop", "structured_outputs", ...]
```

```
# OpenRouter per-endpoint capability (abridged)
provider_name: Cerebras       | tag: cerebras/fp16
  response_format: true | structured_outputs: true | reasoning_effort: true | tools: true
provider_name: DigitalOcean   | tag: digitalocean
  response_format: FALSE | structured_outputs: FALSE
provider_name: SambaNova      | tag: sambanova
  response_format: FALSE | structured_outputs: FALSE
provider_name: Amazon Bedrock | tag: amazon-bedrock
  response_format: FALSE | structured_outputs: FALSE
```

Provider slug confirmed from `GET /api/v1/providers`: `{"name":"Cerebras","slug":"cerebras"}` — **lowercase**, matching the `cerebras` skill.

### Which approach works vs. silently degrades

| Approach | Verdict |
|----------|---------|
| `response_format=<PydanticModel>` | **Works.** LiteLLM metadata says `supports_response_schema: true` for this exact model string, so LiteLLM forwards rather than strips. This is what the project's `cerebras` skill prescribes — keep it. |
| `response_format={"type":"json_schema", ...}` raw dict | Works. Equivalent; more verbose. Use only if you need `strict: true` control. |
| `extra_body={"response_format": {...}}` | Works but **unnecessary now**. This was the 2025 workaround (LiteLLM discussion #11652) for when the OpenRouter adapter stripped `response_format`. That model is now flagged supported. Don't cargo-cult it. |
| `{"type": "json_object"}` (plain JSON mode) | Degrades. Yields *valid JSON of arbitrary shape* — the `trades`/`watchlist_changes` keys may be missing. Do not use. |
| Tool calling | Works but wrong tool for the job. Adds a round-trip and a parse branch for a fixed single-shape response. |
| **`order: ["cerebras"]` without `allow_fallbacks: false`** | **SILENTLY DEGRADES.** `allow_fallbacks` defaults to `true`. Under Cerebras load, OpenRouter reroutes to DigitalOcean/SambaNova/Bedrock, which ignore `response_format` entirely and return prose. `model_validate_json()` then raises on an ordinary user message. **This is the single highest-risk item in the whole stack.** |

### Prescriptive call

```python
import os
from litellm import completion
from pydantic import BaseModel, Field
from typing import Literal

MODEL = "openrouter/openai/gpt-oss-120b"

EXTRA_BODY = {
    "provider": {
        "order": ["cerebras"],
        "allow_fallbacks": False,     # REQUIRED - see table above
        "require_parameters": True,   # belt and braces: reject providers lacking response_format
    }
}

class Trade(BaseModel):
    ticker: str
    side: Literal["buy", "sell"]
    quantity: float

class WatchlistChange(BaseModel):
    ticker: str
    action: Literal["add", "remove"]

class ChatResponse(BaseModel):
    """All three fields required, empty arrays when nothing to do (PLAN.md section 9)."""
    message: str
    trades: list[Trade] = Field(default_factory=list)
    watchlist_changes: list[WatchlistChange] = Field(default_factory=list)

response = completion(
    model=MODEL,
    messages=messages,
    response_format=ChatResponse,
    reasoning_effort="low",
    extra_body=EXTRA_BODY,
)
result = ChatResponse.model_validate_json(response.choices[0].message.content)
```

### Operational notes

- **`allow_fallbacks: False` trades availability for correctness.** If Cerebras is down the call raises instead of returning garbage. That is the right trade here — PLAN.md §5 already requires `/api/chat` to degrade to a normal-shaped response on failure, so wrap the call and return the fallback envelope on exception. Same code path as the missing-API-key case.
- **`reasoning_effort="low"`** is confirmed supported on the Cerebras endpoint. Keep it — gpt-oss-120b is a reasoning model and default effort adds latency for no benefit on this task.
- **`gpt-oss-120b` emits reasoning content.** Read `.choices[0].message.content` only; do not concatenate `reasoning`.
- **`litellm` must be added properly.** It is currently loose in `backend/.venv` and absent from `pyproject.toml`/`uv.lock` — `uv sync --frozen --no-dev` in Docker will therefore **not** install it and the container will `ImportError` at chat time. `uv add litellm pydantic python-dotenv`.

---

## 5. SQLite from Python 3.12 — Prescriptive

**Recommendation: stdlib `sqlite3` + `def` (non-`async`) FastAPI path operations + one connection per request. No aiosqlite. No ORM.**
**Confidence: HIGH** (mechanism verified against FastAPI's async docs).

### Why this is correct, not lazy

FastAPI docs, verbatim: *"When you declare a path operation function with normal `def` instead of `async def`, it is run in an external threadpool that is then awaited, instead of being called directly (as it would block the server)."* And: *"If you are using a third party library that communicates with something (a database...) and doesn't have support for using `await`... then declare your path operation functions as normally, with just `def`."*

So a blocking `sqlite3` call inside a `def` endpoint **does not block the event loop** — AnyIO moves it to a worker thread. The event loop stays free for the SSE stream, which is the only latency-critical path.

`aiosqlite` does not make SQLite async; it wraps the same blocking calls in a background thread and gives you `await` syntax. Identical mechanism, extra dependency, extra concept. For a single-user app this is pure overhead — and it directly violates the project's "do not overengineer" rule.

### The one hard rule

**Never call `sqlite3` from an `async def` endpoint.** Mixing the two is the actual failure mode: an `async def` endpoint holding a blocking DB call stalls the event loop and the price stream visibly stutters for every connected client. Keep DB-touching endpoints `def`; keep SSE `async def`.

### Connection strategy

**One connection per request, via a FastAPI dependency.** Not a shared global connection.

```python
import sqlite3
from pathlib import Path
from collections.abc import Iterator
from fastapi import Depends

DB_PATH = Path(os.environ.get("DB_PATH", "/app/db/finally.db"))

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")      # persistent; survives reconnect
    conn.execute("PRAGMA foreign_keys=ON")       # per-connection; MUST be set every time
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")    # safe under WAL, much faster
    return conn

def get_db() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()

# def, not async def - runs in the threadpool
@router.get("/api/portfolio")
def get_portfolio(db: sqlite3.Connection = Depends(get_db)):
    ...
```

Rationale for connection-per-request: `sqlite3` connections are not thread-safe by default (`check_same_thread=True`), and `def` endpoints run on *arbitrary* threadpool threads. A shared global connection would need `check_same_thread=False` plus a manual lock — which serializes every query and reintroduces the blocking you were avoiding. Per-request connections are cheap (SQLite open is ~microseconds on an already-created file) and thread-correct by construction.

### Pragma notes

| Pragma | Scope | Why |
|--------|-------|-----|
| `journal_mode=WAL` | **Persistent** (stored in the file) | Readers don't block the writer. Essential: the 30s snapshot task writes while requests read. Set once at init; harmless to repeat. |
| `foreign_keys=ON` | **Per-connection, resets every time** | The classic SQLite footgun. Must be in `_connect()`, not just at schema creation. |
| `busy_timeout=5000` | Per-connection | The snapshot background task and a trade request can collide. Without this you get an immediate `database is locked`. |
| `synchronous=NORMAL` | Per-connection | Safe under WAL; materially faster. |

### WAL + Docker bind mount

WAL creates `finally.db-wal` and `finally.db-shm` alongside the DB in the bind-mounted `db/`. Add all three to `.gitignore` (`db/finally.db*`), not just `finally.db`. On Windows hosts, WAL over a bind mount is fine for a single container writer — the known WAL problems are with *network* filesystems (NFS/SMB), which does not apply.

### The background snapshot task is the exception

The 30-second snapshot task runs in the event loop (started from `lifespan`), not in a request threadpool. It must not call `sqlite3` directly. Use `anyio.to_thread.run_sync`:

```python
import anyio

async def snapshot_loop():
    while True:
        await anyio.sleep(30)
        await anyio.to_thread.run_sync(write_snapshot_if_changed)
```

### Alternatives, honestly assessed

| Option | When it would be right | Verdict here |
|--------|------------------------|--------------|
| `aiosqlite` | You need `async def` endpoints for other reasons and want uniform syntax | Rejected — same threads, extra dep, no benefit |
| SQLAlchemy 2.0 (sync) | Complex relational queries, migrations, multiple backends | Rejected — 6 flat tables, no joins beyond trivial. Adds a large dep for negative value |
| SQLModel | You want Pydantic + ORM unified | Rejected — same reason, plus it lags SQLAlchemy releases |
| Python 3.12 `sqlite3` autocommit | New in 3.12; more predictable transactions | Optional. Default (legacy) behavior is fine for six tables; mention only so nobody is surprised by implicit `BEGIN` |

---

## 6. FastAPI — SSE, Lifespan, Static Mount

**Verified against** `fastapi.tiangolo.com/advanced/events/`, `/async/`, and `starlette.io/staticfiles/`. **Confidence: HIGH.**

### SSE: keep what already exists

`backend/app/market/stream.py` already uses plain `StreamingResponse` with `media_type="text/event-stream"` and the right headers (`Cache-Control: no-cache`, `X-Accel-Buffering: no`). **This is current best practice. Do not add `sse-starlette`.** It exists (3.4.8) and is fine, but it would mean rewriting a tested, frozen module to gain nothing — the only thing it adds is automatic client-disconnect handling, which `stream.py` already does via `request.is_disconnected()`.

### Lifespan

`@app.on_event("startup")` is **deprecated**. FastAPI docs: *"If you provide a `lifespan` parameter, `startup` and `shutdown` event handlers will no longer be called. It's all `lifespan` or all events, not both."* Use the `@asynccontextmanager` form shown in section 1 above. Both background tasks (market feed, snapshot loop) start there.

### Mount ordering

Already flagged in PLAN.md §11 and PROJECT.md constraints, and it's real: Starlette matches routes in registration order. `app.mount("/", ...)` registered first swallows everything, and every `/api/*` endpoint 404s while the UI loads perfectly — which is exactly why it wastes so much time. Mount static **last**.

Suggested guard, cheap insurance:

```python
def test_api_not_shadowed_by_static(client):
    assert client.get("/api/health").status_code == 200
```

---

## 7. Playwright 1.62.1 — Host Against Container

**Confidence: HIGH** for version and config shape; **MEDIUM** on the recommendation itself (it is a judgment call, argued below).

### Recommendation: **no `webServer` block.** Use `globalSetup` to health-check instead.

PLAN.md §12 already decided Playwright runs on the host against the container from the normal start script. A `webServer` block that shells out to `docker run` fights that: Playwright would own the container lifecycle, `reuseExistingServer` semantics get murky across platforms, and teardown on Windows PowerShell vs. bash diverges. The plan's instinct is right.

But bare "no webServer" gives a terrible failure mode — if the container isn't up, all specs fail with opaque `net::ERR_CONNECTION_REFUSED`. A tiny `globalSetup` converts that into one clear sentence.

**`test/playwright.config.ts`:**

```ts
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './specs',
  globalSetup: './global-setup.ts',
  fullyParallel: false,          // one shared SQLite portfolio - tests mutate global state
  workers: 1,
  retries: process.env.CI ? 2 : 0,
  reporter: [['html', { open: 'never' }], ['list']],
  use: {
    baseURL: 'http://localhost:8000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
})
```

**`test/global-setup.ts`:**

```ts
export default async function globalSetup() {
  const url = 'http://localhost:8000/api/health'
  for (let i = 0; i < 30; i++) {
    try {
      const r = await fetch(url)
      if (r.ok) return
    } catch { /* not up yet */ }
    await new Promise(r => setTimeout(r, 1000))
  }
  throw new Error(
    'FinAlly container is not responding at http://localhost:8000.\n' +
    'Start it first:  ./scripts/start_mac.sh   (or  ./scripts/start_windows.ps1)\n' +
    'Ensure LLM_MOCK=true is set in .env for deterministic chat tests.'
  )
}
```

Two config choices worth defending:

- **`workers: 1` / `fullyParallel: false`.** There is one SQLite DB, one `"default"` user, one cash balance. Parallel specs buying and selling against a shared $10,000 balance will flake constantly. Serial is not a limitation here, it's correctness.
- **`baseURL`** lets specs use `page.goto('/')` and makes the SSE-resilience test's `page.route('**/api/stream/prices', ...)` block straightforward.

`@playwright/test@1.62.1` also satisfies Next.js 16.3.0's own optional peer (`^1.51.1`), so there's no conflict if the frontend ever adds it.

---

## 8. Frontend Unit Testing — Vitest

**Verified against** `nextjs.org/docs/app/guides/testing/vitest` (page metadata: `version: 16.3.0`, `lastUpdated: 2026-02-11`). **Confidence: HIGH.**

### Vitest over Jest — decided

Next.js documents both, but Vitest wins here on specifics: no `next/jest` transform indirection, native ESM (Recharts ships ESM), and it shares Vite's resolver so `@/*` aliases work via one plugin. Jest with Next 16 + ESM + Recharts means `transformIgnorePatterns` archaeology.

```bash
npm install -D vitest @vitejs/plugin-react jsdom \
               @testing-library/react @testing-library/dom vite-tsconfig-paths
```

**`vitest.config.mts`** (from the official guide, plus a setup file):

```ts
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tsconfigPaths from 'vite-tsconfig-paths'

export default defineConfig({
  plugins: [tsconfigPaths(), react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    globals: true,
  },
})
```

**`vitest.setup.ts`:**

```ts
import '@testing-library/jest-dom/vitest'
```

Note the `/vitest` subpath — `@testing-library/jest-dom` 7.x exposes matchers per-runner. Importing the bare package registers Jest's `expect`, not Vitest's, and every `toBeInTheDocument()` fails with a confusing "not a function".

### React 19 compatibility

`@testing-library/react@16.3.2` peers: `react: "^18.0.0 || ^19.0.0"`. **Clean.** RTL 16 is the React-19-capable line — anything on RTL 14/15 predates it. `@testing-library/dom@^10` is a required *peer* and must be installed explicitly (RTL 16 no longer bundles it) — the #1 cause of "cannot find module @testing-library/dom" on a fresh setup.

### Known caveats for this app

- **Async Server Components are unsupported** in Vitest. Next.js docs, verbatim: *"Vitest currently does not support them... we recommend using E2E tests for async components."* Not a problem — FinAlly is effectively all Client Components (section 1).
- **Recharts needs a sized container in jsdom.** `ResponsiveContainer` measures its parent, which is 0×0 in jsdom, so charts render nothing and assertions fail. Either mock `ResponsiveContainer` in tests or pass explicit `width`/`height`. Test chart *data derivation* as pure functions instead of asserting on SVG output — far more valuable and not brittle.
- **`EventSource` does not exist in jsdom.** Stub it in `vitest.setup.ts` for any component that opens the SSE connection.

---

## 9. Node.js — Use 24, Not 22

**Verified against** `nodejs.org/dist/index.json` and the official `nodejs/Release` `schedule.json`. **Confidence: HIGH.**

| Major | Codename | LTS start | Maintenance | EOL | Status on 2026-08-05 |
|-------|----------|-----------|-------------|-----|----------------------|
| 22 | Jod | 2024-10-29 | **2025-10-21** | 2027-04-30 | Maintenance only |
| **24** | **Krypton** | **2025-10-28** | 2026-10-20 | 2028-04-30 | **Active LTS** |
| 26 | — | 2026-10-28 | 2027-10-20 | 2029-04-30 | Not yet released |

Latest builds: `v24.19.0` (2026-08-03), `v22.23.2` (2026-07-28).

**PLAN.md §11 specifies Node 22 — update it to Node 24.** Node 22 is not broken and would still build the frontend (Next requires `>=20.9.0`, Vitest 4 accepts `^22`), but it receives only critical fixes now, and Node 24 goes to maintenance in Oct 2026 — meaning a Node 22 choice today is *already* the older of two maintained lines.

```dockerfile
# Stage 1
FROM node:24-slim AS frontend
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build          # -> /app/out

# Stage 2
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/ ./
COPY --from=frontend /app/out ./static
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`npm ci` requires `frontend/package-lock.json` to be committed, and `uv sync --frozen` requires `litellm` to actually be in `uv.lock` (see section 4).

---

## Version Compatibility Matrix

| Package | Compatible With | Verified How |
|---------|-----------------|--------------|
| `next@16.3.0` | `react@19.2.8`, `node>=20.9.0` | registry `peerDependencies` + `engines` |
| `recharts@3.10.1` | `react ^19`, `react-is ^19`, `react-dom ^19` | registry `peerDependencies` |
| `@testing-library/react@16.3.2` | `react ^19`, `@testing-library/dom ^10` | registry `peerDependencies` |
| `vitest@4.1.10` | `node ^20 \|\| ^22 \|\| >=24` | registry `engines` |
| `@playwright/test@1.62.1` | Next 16 optional peer `^1.51.1` | registry `peerDependencies` |
| `litellm@1.95.0` | `python >=3.10,<3.15` → **OK with 3.12** | PyPI `requires_python` |
| `pydantic@2.13.4` | `python >=3.9` → OK | PyPI `requires_python` |
| `fastapi@0.141.1` | satisfies existing `>=0.115.0` | PyPI |
| `massive==2.2.0` (pinned) | no conflict with litellm/pydantic 2.x | no shared constraint |
| `numpy>=2.0` (pinned) | no conflict | no shared constraint |
| **`typescript@7.0.2`** | **INCOMPATIBLE with Next 16 default TS path** | TS 7 dropped `lib/typescript.js`; Next 16.3's `experimental.useTypeScriptCli` is preview-only |

### Backend compatibility conclusion

Nothing in the additions conflicts with the frozen market subsystem. `litellm` pulls in `pydantic`, `httpx`, `openai`, and `tokenizers` — none of which constrain `numpy`, `massive`, or `fastapi` in a way that collides. Let `fastapi` float on its existing `>=0.115.0` rather than re-pinning; run the 154 existing tests after `uv add litellm` to confirm no resolver drift.

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `typescript@7.x` (current npm `latest`) | Dropped the JS Compiler API Next.js integrates through; restored in 7.1 | `typescript@^5` |
| `tailwind.config.js` / `content: []` | Does not exist in v4; produces a stylesheet with no utilities | `@theme` in `globals.css` |
| `@tailwind base/components/utilities` | v3 syntax | `@import "tailwindcss";` |
| `tailwindcss` as the PostCSS plugin | v4 split it out | `@tailwindcss/postcss` |
| `aiosqlite` | Same threadpool as `def` endpoints, extra dependency, no gain | stdlib `sqlite3` + `def` endpoints |
| SQLAlchemy / SQLModel | Six flat tables, no joins; large dep for negative value | Raw `sqlite3` + `sqlite3.Row` |
| `sse-starlette` | `StreamingResponse` already works and is already tested here | Existing `stream.py` |
| `@app.on_event("startup")` | Deprecated; silently ignored if `lifespan` is set | `lifespan=` asynccontextmanager |
| `response_format={"type":"json_object"}` | Valid JSON, arbitrary shape — required keys may vanish | `response_format=<PydanticModel>` |
| `order:["cerebras"]` without `allow_fallbacks:False` | Silent reroute to providers that ignore `response_format` | Add `allow_fallbacks: False` |
| Jest for this frontend | ESM + Recharts + Next 16 transform pain | Vitest 4 |
| `webServer` block running `docker run` | Fights the host-runs-against-container decision; cross-platform teardown pain | `globalSetup` health check |
| Recharts v2 snippets from memory | v3 removed `CategoricalChartState`, `activeIndex`, internal cloned props | Build from v3 `.d.ts` |
| `node:22-*` base image | Maintenance LTS since 2025-10-21 | `node:24-slim` |
| Next.js `app/api/**` route handlers | Unsupported under static export where request data is needed | FastAPI `/api/*` |
| Server Actions for trades | Unsupported under static export | `fetch('/api/portfolio/trade')` from a Client Component |

---

## Deltas from PLAN.md

PLAN.md is authoritative for product behavior; these are stack-level corrections only.

| PLAN.md says | Research says | Severity |
|---|---|---|
| §11 "Node 22 slim" | Node 24 is Active LTS; 22 is maintenance | Low — one line |
| §10 "Recharts for every chart" | **Confirmed viable** — Treemap present and typed in 3.10.1 | None — validated |
| §9 LiteLLM structured outputs | Works, but **requires `allow_fallbacks: False`** to not silently degrade | **High — add to LLM phase** |
| §10 "Tailwind CSS with a custom dark theme" | Must be v4 CSS-first `@theme`, not a JS config | Medium — wrong approach costs a debug cycle |
| §5 `.env` at project root | Backend needs `python-dotenv` to load `../.env`; not currently a dependency | Low |
| §12 Playwright on host | Endorsed; add `globalSetup` health check and `workers: 1` | Low |
| (unstated) TypeScript version | Must pin `^5`; `latest` is 7.x and breaks | **High — silent trap** |
| (unstated) dev-mode API proxying | `rewrites` unsupported under export; needs `NEXT_PUBLIC_API_BASE` | Medium |

---

## Confidence Assessment

| Area | Confidence | Basis |
|------|------------|-------|
| npm/PyPI versions | **HIGH** | Direct registry queries, 2026-08-05 |
| Recharts Treemap API | **HIGH** | Extracted from the shipped `recharts@3.10.1` tarball `.d.ts` |
| Node LTS status | **HIGH** | Official `nodejs/Release/schedule.json` |
| OpenRouter/Cerebras structured outputs | **HIGH** | Live OpenRouter `/models`, `/endpoints`, `/providers` + LiteLLM metadata JSON |
| Next.js static export | **HIGH** | Official docs, page reports `version: 16.3.0`, `lastUpdated: 2026-07-21` |
| Tailwind v4 setup | **HIGH** | Official framework guide + theme docs |
| FastAPI lifespan / threadpool / StaticFiles | **HIGH** | Official FastAPI + Starlette docs, verbatim quotes |
| Vitest + RTL | **HIGH** | Official Next.js guide (`lastUpdated: 2026-02-11`) + registry peers |
| TypeScript 7 incompatibility | **MEDIUM-HIGH** | Registry facts are certain (`latest` = 7.0.2, `create-next-app` scaffolds `^5`); the "no JS API until 7.1" detail came from secondary sources. **The mitigation — pin `^5` — is correct regardless.** |
| SQLite recommendation | **HIGH** (mechanism) / **MEDIUM** (judgment) | FastAPI threadpool behavior is documented verbatim; "no ORM" is a defensible design call, not a fact |
| Playwright config shape | **HIGH** (API) / **MEDIUM** (recommendation) | Options verified from docs; `globalSetup`-over-`webServer` is a judgment call |

**Note on tooling:** Context7 MCP and all external search providers are disabled in `.planning/config.json`, so the `research-plan` seam routed to `websearch`/`webfetch`, which `classify-confidence` tiers as LOW. Findings sourced from **live package registries, the OpenRouter API, and shipped package artifacts** are rated higher than that default, because those are primary sources rather than search results. Items resting on blog/search evidence alone are flagged MEDIUM above.

---

## Open Questions for Later Phases

1. **Cerebras availability under `allow_fallbacks: False`** — untested against the real key. The chat phase should verify a live call succeeds and that the failure path returns PLAN.md's degraded envelope rather than a 500.
2. **Recharts Treemap with a single position** — a one-node treemap is a degenerate layout; needs a visual check during the charts phase.
3. **`pytest>=8.3.0` floating to 9.1.1** — a major bump under the existing constraint. Run the 154 tests before assuming it's transparent.
4. **WAL over a Windows Docker Desktop bind mount** — expected fine (single writer, not a network FS) but worth one explicit check on the target machine during the Docker phase.

---

*Stack research for: single-container AI trading workstation*
*Researched: 2026-08-05*
