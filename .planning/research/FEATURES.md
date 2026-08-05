# Feature Research

**Domain:** Paper-trading terminal with an AI copilot (single-user, simulated money, local demo)
**Researched:** 2026-08-05
**Confidence:** MEDIUM (cross-checked across multiple live products and vendor docs; no primary user research)

Scope note: the market data subsystem is already built and is out of scope. This covers the simulated portfolio, trading, portfolio visualization, watchlist, and the LLM copilot.

---

## Executive Findings

Six findings drive everything below. Each is a concrete deviation between PLAN.md and how real products behave.

1. **`change_from_open_percent` is the right number, but "Change %" is the wrong label.** Every mainstream ticker computes day change against *previous close*. FinAlly's baseline is "first price after process start". A column headed **Change %** will be silently misread. Label it **Chg from Open** or **Session %**.
2. **Flash color and cell color encode two different things in real terminals, and PLAN.md currently conflates them.** The transient flash encodes *tick direction*; the persistent color encodes *session change*. PLAN.md section 10 routes the flash through `change_from_open_percent`, which makes a downtick flash green whenever the ticker is up on the session. That reads as a bug.
3. **The treemap is empty at 0 positions and degenerate at 1.** That is the default first-run state and the state immediately after the first demo trade. Unhandled, the single largest visual differentiator looks broken exactly when the demo starts.
4. **The P&L chart with one seeded snapshot renders nothing.** A line needs two points. "One snapshot at seed time" is necessary but not sufficient.
5. **Reset Portfolio is missing and is table stakes.** TradingView, thinkorswim, Webull and Investopedia all have it. In an auto-executing AI product it is also the *substitute for a confirmation dialog* — the thing that makes irreversibility not matter.
6. **Auto-execution is correct here, but only if the receipt is loud.** Human-in-the-loop guidance gates on reversibility and cost, both of which are zero with fake money. What must not be dropped is the *tool-call render pattern*: the transcript must show what was executed, at what price, and whether it succeeded — because the LLM's prose is written before the trade result is known and will sometimes be wrong.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features whose absence reads as **broken**, not as **deliberately simple**.

| Feature | Why Expected | Complexity | Notes / Dependency |
|---------|--------------|------------|--------------------|
| Positions table: ticker, qty, avg cost, current price, unrealized P&L ($ and %) | This exact column set is the industry floor — Webull's Positions tab, thinkorswim's position page, TradingView's Positions tab all show it. A missing avg-cost column is the one users notice first | LOW | Requires portfolio API + live price map. Already in PLAN.md §10 |
| Cash balance + total account value, both live | Webull's "Account Details" shows virtual capital, P/L and portfolio value as one block. Users check the number before and after every trade | LOW | Requires `/api/portfolio` + SSE recompute. Already in PLAN.md §10 header |
| **Visible fill confirmation after a trade** | thinkorswim onboarding guidance is explicitly "place small orders until tickets, confirmations, and position pages feel familiar". A trade that silently mutates a table does not feel like a trade | LOW | `POST /api/portfolio/trade` already returns `fill_price`. **Needs a UI surface** (toast or inline row) — PLAN.md specifies the data but not the moment |
| Watchlist with live price + change % | Present in every paper account surveyed; both thinkorswim and Webull treat watchlist building as a first-session skill | LOW | Already specified |
| Add / remove watchlist ticker | The first thing a user does after seeing 10 defaults is add their own symbol | LOW | Already specified. Unknown-ticker synthesis (already built) is what makes this not dead-end |
| Sparkline per watchlist row | Data-dense terminals never show a bare number where a shape fits | MEDIUM | Requires the ~60-point backfill (already built) |
| Main chart for a selected ticker | Clicking a row and getting a bigger chart is the single most-attempted interaction in any watchlist UI | MEDIUM | Requires watchlist history + SSE extension. **Must auto-select on first paint** — see First-Run below |
| Portfolio value over time (P&L curve) | "Am I up or down since I started" is the question the whole product exists to answer | MEDIUM | Requires `portfolio_snapshots`. See the one-point problem below |
| **Total return vs. starting $10,000, in $ and %** | Compensates for the deliberate absence of realized P&L. Webull shows realized and unrealized side by side; without *either*, a profitable round-trip vanishes without trace | LOW | Pure client arithmetic: `total_value - 10000`. **Not currently in PLAN.md** |
| **Reset portfolio to $10,000** | TradingView lets you reset the paper account to any balance; thinkorswim, Webull and Investopedia all offer a reset. In a simulator this is the primary recovery action | LOW | One `POST /api/portfolio/reset`: clear positions, restore cash, optionally clear chat. **Not currently in PLAN.md** |
| Insufficient-cash / insufficient-shares errors shown verbatim | Every simulator rejects these. A silent failure or a raw 400 is the classic "broken" signal | LOW | PLAN.md §8 already writes messages for verbatim display — good |
| Connection status that distinguishes *quiet* from *stalled* | The documented failure mode of every trading platform is the green dot that stays green while the feed silently froze (NinjaTrader is the canonical example) | LOW | PLAN.md's heartbeat + 30s silence rule already solves this correctly. Validate as good |
| Chat history surviving reload | AI chat transcripts are treated as durable state, not ephemeral UI | LOW | `GET /api/chat` already specified |
| Green/red semantics used consistently across every surface | Western convention: green up, red down. Inconsistency between table, heatmap and chart is instantly noticed | LOW | Enforce one shared color function |

### Differentiators (What Makes This Impressive)

| Feature | Value Proposition | Complexity | Notes / Dependency |
|---------|-------------------|------------|--------------------|
| **AI executes trades with no confirmation dialog** | This is the entire capstone thesis. Every AI trading product surveyed (MiDash, Alphio, LCX, TradingView AI Copilot) advertises exactly this. Zero-stakes fake money is what makes it defensible | MEDIUM | Requires trade execution + structured outputs. Legitimacy depends entirely on the receipt below |
| **Inline action receipts in the transcript** | The documented "tool-call render pattern" — name the action, its arguments, and the actual result. Described in the sources as "the difference between an agent and a magic trick" | MEDIUM | Requires `actions` JSON on `chat_messages` (already in schema). Must render **per-action success/failure**, see Pitfall below |
| **AI manages the watchlist** | Moves the copilot from "chatbot that answers" to "agent that operates the app". Cheap given the endpoints exist | LOW | Requires watchlist API + structured outputs |
| **AI grounded in live portfolio numbers** | The difference between a generic LLM and a copilot is that it cites *your* cash, *your* concentration, *your* P&L. Sage Copilot's stated trust requirement is "complete, real-time data from the system of record" | MEDIUM | Requires portfolio context injection (already in PLAN.md §9) |
| **Portfolio treemap sized by weight, colored by P&L** | The Finviz map is the most recognizable object in retail finance. Two encodings — size = importance, color = performance — in one glance | MEDIUM | Requires positions + live prices + Recharts Treemap. **Needs a low-N fallback**, see below |
| **Whole loop live off one SSE stream** | Header total, positions P&L, heatmap colors and the live end of the P&L line all recompute from one price frame with no polling. This is what makes it feel like a terminal rather than a dashboard | MEDIUM | Requires SSE + client-side valuation (PLAN.md §10 — a genuinely strong design choice) |
| Flash-on-tick price animation | Real terminals pulse Bid/Ask/Last green on uptick, red on downtick, decaying back to theme color. It is the cheapest "this is live" signal that exists | LOW | Requires `direction` on the SSE payload (already present) |
| Deterministic `LLM_MOCK` mode | Makes the agentic feature E2E-testable, which is itself part of the capstone's argument | LOW | Already specified as a contract in PLAN.md §9 |
| One-command Docker launch | The demo's first 30 seconds. Nothing else matters if this fails | MEDIUM | Already specified |

### Anti-Features (Tempting, But Traps at This Scope)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Confirmation dialog on AI trades** | "Surely you confirm before trading" | Kills the demo and buys nothing. HITL guidance gates on *reversibility and cost* — both zero here. Alarm fatigue is documented: users stop reading prompts after ~50 approvals, so blanket confirmation actively reduces safety | Auto-execute + loud receipt + **Reset Portfolio** as the undo |
| **Limit / stop / bracket orders** | TradingView paper trading has all of them; Webull users complain about their absence | Requires an order book, resting-order lifecycle, partial fills and a matching engine against a GBM tick stream that has no depth. Enormous cost, zero contribution to the core loop | Keep market-only, but **label the trade bar "Market order — instant fill"** so the omission reads as a choice. Webull's complaint lands because Webull is a *broker*; FinAlly is openly a simulator |
| Shorting / margin | "Real traders short" | Doubles portfolio math (negative quantities, buying power, maintenance) and creates the possibility of a negative account | Long-only. No user of a $10k educational sim expects it |
| **Realized P&L column** | Webull shows realized and unrealized side by side | Requires lot tracking or a cost-basis method (FIFO vs average) — a real decision with real code. But excluding it *entirely* leaves profitable round-trips invisible | **Total return vs. $10,000 starting** in the header. One subtraction, covers 95% of the need. The `trades` audit log preserves the option |
| Order book / depth / Time & Sales tape | The most Bloomberg-looking panel there is | Would be pure fabrication — a GBM simulator has no bids, asks, or prints. Also note the tape uses green/red for *uptick vs. trade-at-ask*, a third meaning that would collide with the existing two | Skip. The flash animation already delivers the "tape is moving" feeling honestly |
| Candlestick / OHLC main chart | Every trading app has candles | The feed emits ticks, not bars. Synthesizing OHLC from 500ms GBM ticks produces candles that mean nothing and invite technical reading of noise | Line/area chart, which is honest about being a tick series |
| Technical indicators (MA, RSI, MACD, volume) | Looks professional; two lines of Recharts | Indicators on synthetic GBM data are numerology. Users *will* read signals into them. Also: no volume exists in the feed | Skip entirely. If one is wanted, a session VWAP-style mean line is the only defensible option |
| Multi-timeframe selector (1D / 1W / 1M / 1Y) | Universal chart convention | Only session-length data exists. Four buttons that all render the same series is a textbook "broken" signal — worse than having no buttons | Single implicit "session" timeframe, no selector |
| News feed / fundamentals / earnings panel | Fills the Bloomberg-shaped hole in the layout | Needs a second data provider, an API key, caching, and off-hours behavior. Contributes nothing to watch→trade→visualize→chat | Give the space to the chat panel — the actual differentiator |
| Price alerts / notifications | Natural watchlist companion | Needs persistence, evaluation loop, and a delivery channel. On a 500ms simulated feed alerts fire constantly and become noise | Skip. The AI answering "tell me if NVDA moves" conversationally is the on-theme version |
| AI autonomous / scheduled trading mode | "Let the agent trade for me" — the obvious next step | Turns a demo into an unattended process that burns tokens and drifts the portfolio while nobody watches. Also removes the human from a loop whose whole point is showing the human-agent interaction | Keep the agent turn-based and user-initiated |
| Backtesting / strategy replay | thinkorswim and MiDash both have it | An entire second product. Requires historical data the simulator does not have | Out of scope, explicitly |
| Sector grouping inside the treemap | Finviz groups tiles by sector | Requires a sector taxonomy for arbitrary user-added tickers, which the simulator cannot synthesize meaningfully | Flat treemap. Position count is small enough that grouping adds nothing |
| Multiple named watchlists | Standard in every real platform | Multiplies watchlist state, selection state, and the AI's addressing problem, for one user with ten tickers | One watchlist |
| Token-by-token chat streaming | Standard ChatGPT feel | Already excluded, correctly — Cerebras is fast enough. Streaming also *conflicts* with structured outputs, since a partial JSON object is not renderable | Loading indicator. Make it name what it is doing ("Analyzing portfolio…") rather than a bare spinner |
| Trade history panel | The `trades` table already exists | Genuinely cheap (one GET, one table) but adds a seventh panel to a screen that is already dense, and duplicates information the fill toast and chat receipts already give | Keep excluded at MVP. Note it as the cheapest available "feels complete" addition if a panel ever feels thin |

---

## Domain Conventions That Will Be Misread If Gotten Wrong

These are correctness issues, not preferences.

### 1. "Change %" means change from previous close

Standard formula across tickers and charts: `(current − previous_close) / previous_close × 100`. A minority of screeners use open-to-close, and day traders separately track a *distinctly labeled* "Chg from Open (%)". Tick-over-tick change is not a column any product exposes.

FinAlly's `change_from_open_percent` is the right *value* — it is stable, meaningful, and survives reconnects. But its baseline is "first price after process start", which for a container started at 3pm means "change since 3pm".

**Action:** label the column **`Chg from Open`** or **`Session %`**, never bare `Change %`. Consider a tooltip: "since this session started". Cost: a string.

### 2. Flash color and cell color are two different signals

Real terminals do both simultaneously:
- **Transient flash** (~500ms decay) = *tick direction* — green on uptick, red on downtick, relative to the **previous price**.
- **Persistent cell color** = *session/day change* — green if up on the session, red if down.

PLAN.md §10 states the price-flash coloring uses `change_from_open_percent`. That produces a green flash on a *downtick* whenever the ticker happens to be up on the session — which is exactly the misread this convention exists to prevent.

**Action:** flash from `direction` / `change` (tick-over-tick, already on the payload); color the change column from `change_from_open_percent`. Both fields are already in the SSE frame, so this is a wiring decision, not new work.

Secondary convention: the **tick rule** — a print equal to the previous print inherits the previous color rather than going neutral. Cheap to honor; prevents a flicker to gray on flat ticks.

### 3. Bloomberg density is about *liveness*, not clutter

Bloomberg's stated design principle is information density, keyboard shortcuts, and minimal click latency — "shave seconds off common tasks". The trap is imitating the *look* (tiny fonts, packed grids) without the substance. Also worth internalizing: real Bloomberg users run **two to six monitors**. A single browser tab cannot be a Bloomberg terminal and should not try.

**Action:** the core loop (watch → trade → see portfolio react) must fit one 1080p viewport with **no scrolling**. Every panel must contain live numbers. Density is earned by liveness, not by font size.

### 4. Treemap encoding conventions

Finviz: rectangle **size** = market cap (relative importance), **color** = percent change on a **diverging green↔red gradient centered on zero**, with saturation encoding magnitude.

Portfolio translation: **size = position market value** (portfolio weight), **color = unrealized P&L %**.

Two things finance users specifically expect:
- Color is a **gradient, not a binary**. Flat green for +0.1% and +30% throws away the whole point.
- The gradient must be **centered at 0%** and **symmetric**, so +2% and −2% are equally saturated. Clamp the scale (e.g. ±5%) so a single outlier position does not wash the rest to gray.
- Tiles need a **ticker label plus the P&L %** in-tile. An unlabeled treemap is decoration.

---

## The Low-N and Empty-State Problem (Answers Q3 and Q6)

### Treemaps break at low item counts

Storytelling with Data, Tableau, NN/g and The Information Lab all converge: treemaps earn their place with **many** related categories and/or hierarchy. At low density, bar charts produce significantly lower comparison error. At **1 item**, a treemap is a single colored rectangle carrying zero comparative information.

FinAlly's default states are exactly the broken ones:

| Positions | What the treemap shows | Verdict |
|-----------|------------------------|---------|
| 0 (fresh account) | Nothing | Reads as broken |
| 1 (after the first demo trade) | One rectangle filling the panel | Reads as broken |
| 2–3 | Crude but legible | Acceptable |
| 4+ | Works as intended | Good |

**Recommendation:** the heatmap panel is a small state machine, not a chart.
- **0 positions** → explicit empty state: "No positions yet — buy something to see your portfolio here." Per empty-state guidance: say *why* it is empty and give *one* action.
- **1–2 positions** → still render the treemap, but the tile must carry ticker, weight %, market value and P&L % so it works as a *card* rather than a comparison. Do not swap chart types at N=3 — a panel that changes shape mid-demo is worse than one that is briefly simple.
- **3+** → the intended treemap.

Cost: LOW. Value: this is the panel a viewer looks at first.

### Assessment: is the current first-run seeding sufficient? **No.**

PLAN.md seeds sparklines (~60 points) and one portfolio snapshot. Auditing all panels on first paint of a fresh database:

| Panel | First-paint state | Alive? |
|-------|-------------------|--------|
| Watchlist (10 tickers, prices, sparklines) | Populated by seed + backfill | ✅ Solid |
| Header cash / total value | $10,000 | ✅ |
| Prices flashing | Simulator publishes within ~500ms | ✅ |
| Connection dot | Green on first frame | ✅ |
| **Main chart** | **Empty — no ticker is selected** | ❌ Largest panel on screen, blank |
| **P&L chart** | **One snapshot → a line chart with one point draws no line** | ❌ Blank |
| **Positions table** | Empty | ⚠️ Correct, but needs a designed empty state |
| **Heatmap** | Empty | ⚠️ Same |
| **Chat panel** | Empty transcript | ⚠️ Same |

**Three of six panels are blank on first paint, and two of them look like failures rather than choices.** Fixes, all LOW cost:

1. **Auto-select the first watchlist ticker** so the main chart renders immediately. Its history comes from the same `/api/watchlist` array — no new endpoint. *This is the single highest-value first-run fix.*
2. **Make the P&L chart survive one point.** Either backfill a short flat series at seed time, or render an explicit dot + reference line at $10,000 and let the live SSE-derived point extend it. A flat line at $10k with a live right edge reads as "tracking, nothing has happened yet" — which is true and looks intentional.
3. **Write three real empty states** (positions, heatmap, chat) with consistent styling. Empty-state guidance is emphatic that the user's first question is "is this broken, or did I do something wrong?" — and that several simultaneously blank widgets read as a failed load unless they are visually deliberate. Consistency across the three is what sells it.
4. **Seed one chat message from the assistant** ("I can analyze your portfolio or place trades — try 'buy 10 shares of NVDA'"). Doubles as discoverability for the differentiating feature and costs one seeded row.

---

## AI Copilot Trust Model (Answers Q4)

### Auto-execution: when it is delightful vs. alarming

The literature gates confirmation on **reversibility, cost, and blast radius** — require approval when an action is hard to reverse, spends money, contacts other people, or changes production systems. FinAlly's trades are reversible (sell it back), spend nothing real, contact nobody, and touch a local SQLite file. **Auto-execution is the correct call and is well-supported.**

The counter-evidence is worth naming honestly: GitHub Copilot CLI's zero-approval execution is a documented security incident, and Microsoft's agent-security guidance warns about agents moving "from reading to acting". Those concerns are about *real-world side effects*. Fake money in a local container has none. The exclusion is safe — but the reasoning is "zero stakes", not "confirmations are bad".

**What must not be dropped:** trust in agentic UIs comes from *legibility after the fact*, not from a prompt beforehand.

### The receipt pattern

Production AI chat surfaces tool calls as first-class UI events in three phases: **initiation** (name the action and its arguments), **execution** (a live status), **completion** (a distinct result component showing the data the agent actually received). FinAlly's non-streaming design collapses this to one step — which makes the completion card the *only* trust surface, so it has to be good.

Minimum per executed action, rendered as a distinct block inside the assistant turn (not as prose):

```
✅ BOUGHT  10 NVDA @ $184.22    −$1,842.20    cash → $8,157.80
❌ SELL    50 TSLA               rejected: insufficient shares (hold 10)
✅ ADDED   PYPL to watchlist
```

Non-negotiable properties:
- **Server-side truth.** Show the actual `fill_price` the server returned, never the price the LLM proposed. This is what proves the AI went through the same path a human click does.
- **Persisted.** The `actions` JSON column already exists — render from it on reload so the transcript is durable, matching the convention that tool calls are durable state.
- **Visually distinct from prose.** A trade rendered as a sentence is indistinguishable from a trade the model merely *claimed* to make.

### The failure trap (important)

PLAN.md §9 says a failed trade's error "is included in the chat response so the LLM can inform the user." Note the ordering problem: the LLM writes `message` **before** the trades are executed. So the prose will say *"I've bought 10 NVDA for you"* while the receipt says *rejected: insufficient cash*. The transcript then contradicts itself, which is the single fastest way to destroy trust in an agent.

**Recommendation:** the `actions` payload must carry per-action `status` and `error`, and the UI must render failures with visibly different treatment (red, ❌) so the receipt visually overrides the prose. Optionally append a system-generated line — *"1 of 2 actions failed"* — above the assistant's text. Do **not** attempt a second LLM round-trip to rewrite the message; it doubles latency for a case a badge solves.

### Where trust breaks generally

- Actions the user cannot see or undo → solved by receipts + Reset.
- The AI asserting numbers that disagree with the panels → solved by injecting live portfolio context (already specified). Concentration and P&L claims must come from the same computation the positions table uses.
- The AI hallucinating a ticker → the simulator accepting unknown tickers (already built) converts a hard failure into a graceful one. Genuinely good design.
- Silence about what it did. An empty `trades` array should still produce a legible "no actions taken" state rather than ambiguity.

---

## Validation of PLAN.md's Existing Exclusions

| Exclusion | Verdict | Reasoning |
|-----------|---------|-----------|
| Limit orders, order books, partial fills, fees | ✅ **Safe** | Requires a matching engine against a feed with no depth. Add the label "Market order — instant fill" so it reads as deliberate |
| Shorting, margin | ✅ **Safe** | Zero expectation in an educational $10k sim; halves the portfolio math |
| Realized P&L tracking/display | ⚠️ **Safe only with mitigation** | Webull shows realized and unrealized together. Without *either*, a profitable round-trip leaves no trace. **Add "Total return vs. $10,000" to the header** — one subtraction closes the gap |
| Trade history UI panel | ✅ **Safe** | Fill toasts + chat receipts provide the audit trail a user actually looks for. Cheapest available addition if a panel later feels thin |
| Authentication / multi-user | ✅ **Safe** | Local single-operator demo; `user_id` preserves the option |
| Token-by-token streaming | ✅ **Safe, and correct for a second reason** | Partial JSON from a structured output is not renderable — streaming would actively fight the schema |
| Second charting library | ✅ **Safe** | One visual language matters more than a marginally better treemap |
| WebSockets | ✅ **Safe** | Nothing flows client→server on the hot path |
| Mobile-first | ✅ **Safe** | Bloomberg-alikes are desktop instruments by definition |
| Cloud deployment | ✅ **Safe** | No demo value |

**Net: one exclusion needs a cheap compensating feature (total return), and two new table-stakes items are missing entirely (Reset Portfolio, visible fill confirmation).**

---

## Feature Dependencies

```
[SQLite schema + lazy init]
    ├──requires──> nothing
    │
    ├──> [Portfolio API: GET /api/portfolio]
    │        ├──> [Header: cash, total value, TOTAL RETURN vs $10k]
    │        ├──> [Positions table]
    │        │        └──> [Portfolio treemap]  (weights + P&L)
    │        └──> [Reset Portfolio]                    <-- NEW
    │
    ├──> [POST /api/portfolio/trade]
    │        ├──> [Trade bar]
    │        ├──> [Fill confirmation surface]          <-- NEW (UI moment)
    │        └──> [Snapshot-on-trade]
    │                 └──> [P&L chart]
    │
    ├──> [portfolio_snapshots + 30s task]
    │        └──> [P&L chart]  (needs >= 2 points to draw)
    │
    └──> [Watchlist API]
             ├──> [Watchlist panel + sparklines]
             │        └──> [Main chart]  (reuses the same history array)
             └──> [AI watchlist management]

[SSE price stream]  (BUILT)
    ├──enables──> [Flash animation]        (uses `direction` / tick delta)
    ├──enables──> [Chg from Open column]   (uses change_from_open_percent)
    ├──enables──> [Client-side live valuation]
    │                 └──> header total, positions P&L, heatmap color, live P&L edge
    └──enables──> [Connection status dot]  (heartbeat + 30s silence rule)

[Chat API]
    ├──requires──> [Portfolio API]   (context injection)
    ├──requires──> [Watchlist API]   (context injection)
    ├──requires──> [Trade execution]  (auto-exec through the SAME path)
    └──> [Inline action receipts]
             └──requires──> per-action status/error in the `actions` payload

[LLM_MOCK] ──enables──> [E2E tests of the agentic path]

[Confirmation dialog] ──conflicts──> [Auto-execution demo]
[Candlesticks / indicators] ──conflicts──> [GBM tick feed honesty]
[Timeframe selector] ──conflicts──> [Session-only data]
```

### Dependency Notes

- **Main chart requires no new endpoint.** `GET /api/watchlist` already returns ~60 history points per ticker; the main chart seeds from that array and extends from SSE, exactly as the sparklines do. This removes what looks like a missing endpoint from the roadmap.
- **Treemap requires the positions table's math, not its own.** Both derive from `cash + Σ(qty × live price)`. Sharing one derivation function prevents the "heatmap and table disagree" bug, which is fatal to trust in a data terminal.
- **P&L chart requires ≥2 snapshots to draw a line.** The seed snapshot alone yields an invisible chart. Either backfill or render the single point explicitly.
- **Chat auto-execution must route through the manual trade path.** PLAN.md already mandates this; it is also what makes an `LLM_MOCK` E2E test a genuine test of trade logic.
- **Fill confirmation depends only on the trade response**, which already carries `fill_price`. This is a UI moment, not backend work.
- **Reset Portfolio depends only on the DB layer** — it can ship in the same phase as the portfolio API, before any frontend exists.

---

## MVP Definition

### Launch With (v1) — the demo is not a demo without these

- [ ] Portfolio API + trade execution with full rule set — the loop's spine
- [ ] Positions table (ticker, qty, avg cost, current price, unrealized P&L $ and %)
- [ ] Header: cash, total value, **total return vs. $10,000**, connection dot
- [ ] Trade bar labeled "Market order — instant fill", with a **visible fill confirmation**
- [ ] Watchlist panel: live price, **`Chg from Open`** column, sparkline, add/remove
- [ ] Flash animation driven by **tick direction**, cell color by **session change**
- [ ] Main chart with **auto-selected first ticker on load**
- [ ] P&L chart that renders meaningfully with one snapshot
- [ ] Portfolio treemap with a designed 0-position empty state and a legible 1-position tile
- [ ] Chat panel with history, loading indicator, and **inline per-action receipts including failures**
- [ ] AI trade + watchlist auto-execution through the shared validation path
- [ ] `LLM_MOCK` deterministic mode
- [ ] **Reset Portfolio**
- [ ] Empty states for positions, heatmap and chat, styled consistently
- [ ] Docker one-command launch

### Add After Validation (v1.x)

- [ ] Seeded assistant greeting message — trigger: the chat panel tests as undiscoverable
- [ ] Trade history panel — trigger: a layout region feels thin, or users ask "what did I do earlier"
- [ ] Keyboard shortcuts (ticker jump, buy/sell focus) — trigger: the Bloomberg "minimal click latency" convention becomes noticeable in demos
- [ ] Per-symbol staleness indication in the watchlist — trigger: real Massive data is used off-hours
- [ ] Configurable starting balance on reset (TradingView does this) — trigger: users want to demo a bigger book

### Future Consideration (v2+)

- [ ] Realized P&L with an explicit cost-basis method — defer: total return covers the need at a fraction of the cost
- [ ] Limit orders — defer: needs a matching engine; changes the product category
- [ ] Sector grouping in the treemap — defer: needs a taxonomy the simulator cannot synthesize
- [ ] Multiple watchlists — defer: no user need at N=1 user, 10 tickers

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Positions table with the standard columns | HIGH | LOW | **P1** |
| Trade execution + fill confirmation surface | HIGH | LOW | **P1** |
| Auto-select first ticker on load (main chart non-blank) | HIGH | LOW | **P1** |
| Correct flash-vs-cell color separation | HIGH | LOW | **P1** |
| `Chg from Open` labeling (not "Change %") | MEDIUM | LOW | **P1** |
| Total return vs. $10,000 in header | HIGH | LOW | **P1** |
| Inline AI action receipts with per-action status | HIGH | MEDIUM | **P1** |
| Treemap low-N + empty-state handling | HIGH | LOW | **P1** |
| P&L chart renders with one snapshot | MEDIUM | LOW | **P1** |
| Reset Portfolio | HIGH | LOW | **P1** |
| Watchlist add/remove | HIGH | LOW | **P1** |
| AI trade + watchlist auto-execution | HIGH | MEDIUM | **P1** |
| Sparklines | MEDIUM | MEDIUM | **P1** (backfill already built) |
| Designed empty states (positions, heatmap, chat) | MEDIUM | LOW | **P1** |
| Seeded assistant greeting | MEDIUM | LOW | **P2** |
| Trade history panel | LOW | LOW | **P2** |
| Keyboard shortcuts | MEDIUM | MEDIUM | **P2** |
| Configurable reset balance | LOW | LOW | **P3** |
| Realized P&L | MEDIUM | HIGH | **P3** |
| Limit orders / indicators / candlesticks / news / alerts | LOW | HIGH | **Never (this scope)** |

---

## Competitor Feature Analysis

| Feature | TradingView Paper | thinkorswim paperMoney | Webull paperTrade | Finviz | **FinAlly's approach** |
|---------|-------------------|------------------------|-------------------|--------|------------------------|
| Starting balance | Configurable | $100,000 | $1,000,000 | — | $10,000 fixed — small enough that a 10-share buy visibly moves the portfolio |
| Order types | Market, limit, stop, bracket | Full | Market/limit (no stop/TP — a noted complaint) | — | **Market only**, explicitly labeled |
| Positions view | Positions tab with account summary | Position page + P&L analysis | Positions tab: unrealized P/L, avg cost, market value | — | Same column set — this is the floor |
| Realized vs unrealized P&L | Both | Both | Both, side by side in Account Details | — | Unrealized only, **plus total-return-vs-$10k** as compensation |
| Account reset | Reset to any balance | Reset available | Reset available | — | **Reset to $10,000** (currently missing from the spec) |
| Watchlist | Yes | Yes, taught as a first-session skill | Yes, first-class in the paper account | — | Yes, plus AI-managed |
| Treemap heatmap | Sector heatmaps | — | — | Size = market cap, color = % change on a diverging gradient | **Size = position weight, color = unrealized P&L %**, clamped diverging scale |
| Trade log | Auto-logged for review | Yes | Yes | — | DB audit log, **no UI** (deliberate) |
| AI copilot | AI Chart Copilot (beta) — chat orders, positions, P&L | — | — | — | **Core feature**, auto-executing, with receipts |
| Confirmation before AI trades | n/a | n/a | n/a | — | **None** — reset is the undo |

The pattern across all four: the *table stakes* are positions, cash, watchlist, reset, and a fill confirmation. The *differentiator space* is entirely in the AI copilot, which only TradingView has and only in beta. That is where this project should spend its ambition.

---

## Sources

Verified across multiple independent sources (confidence MEDIUM per `classify-confidence --provider websearch --verified`):

- Paper trading products: [thinkorswim paperMoney (Schwab)](https://www.schwab.com/trading/thinkorswim/paper-trading), [Webull paperTrade](https://www.webull.com/paper-trading), [TradingView Paper Trading — main functionality](https://www.tradingview.com/support/solutions/43000516466-paper-trading-main-functionality/), [How to Paper Trade on TradingView (Vantage)](https://www.vantagemarkets.com/en/academy/how-to-paper-trade-on-tradingview/), [Webull paper trading guide (GoatFundedTrader)](https://www.goatfundedtrader.com/blog/how-to-use-webull-paper-trading), [thinkorswim paper trading (newtrading.io)](https://www.newtrading.io/thinkorswim-paper-trading/)
- Terminal UI conventions: [How Bloomberg Terminal UX designers conceal complexity](https://www.bloomberg.com/company/stories/how-bloomberg-terminal-ux-designers-conceal-complexity/), [Innovating a modern icon (Bloomberg)](https://www.bloomberg.com/company/stories/innovating-a-modern-icon-how-bloomberg-keeps-the-terminal-cutting-edge/), [Bloomberg Terminal (Wikipedia)](https://en.wikipedia.org/wiki/Bloomberg_Terminal), [Webull: colors in Time & Sales](https://www.webull.com/help/faq/1138-What-do-the-different-colors-in-Time-Sales-data-represent), [XT PriceLine: dynamic colors per tick](https://www.xabcdtrading.com/blog/xt-priceline-dynamic-colors-that-let-you-see-every-tick/)
- Change-% semantics: [Stock Price — Day's Change (%)](https://help.dividenddata.com/en/articles/8756294-stock-price-day-s-change), [Percent Change (Stockopedia)](https://www.stockopedia.com/ratios/percent-change-983/), [Official daily open and close prices (TrendSpider)](https://trendspider.com/learning-center/official-daily-open-and-daily-close-prices/)
- Treemaps/heatmaps: [Finviz Map: A Comprehensive Guide](https://finviz.blog/finviz-map-a-comprehensive-guide/), [Finviz heatmap blog](https://finviz.com/blog/tag/heatmaps/), [Treemaps: pros, cons, alternatives (Storytelling with Data)](https://www.storytellingwithdata.com/blog/2018/6/5/an-alternative-to-treemaps), [An Alternative to Tree-Maps (Tableau)](https://www.tableau.com/blog/alternative-tree-maps-0), [Treemaps (NN/g)](https://www.nngroup.com/articles/treemaps/), [Treemap vs Bar chart (The Information Lab)](https://www.theinformationlab.co.uk/2014/12/16/treemap-vs-bar-chart-end-treemap/)
- AI copilot trust and HITL: [Human in the loop pattern (AI UX Playground)](https://aiuxplayground.com/pattern/human-in-the-loop/), [Reframing LLM Agent Security as an Agent–Human Interaction Problem (arXiv)](https://arxiv.org/html/2605.24309v1), [Securing AI agents (Microsoft Security)](https://www.microsoft.com/en-us/security/blog/2026/06/30/securing-ai-agents-ai-tools-move-from-reading-acting/), [AI in Finance: Can You Trust the Copilot? (Zuora)](https://www.zuora.com/subscribed/ai-in-finance-can-you-trust-the-copilot/), [Sage Copilot](https://www.sage.com/en-us/sage-copilot/)
- Tool-call rendering: [The 'tool-call' Render Pattern](https://dev.to/programmingcentral/the-tool-call-render-pattern-turning-your-ai-from-a-chatty-bot-into-a-doer-4cb2), [AI SDK UI: Chatbot Tool Usage](https://ai-sdk.dev/docs/ai-sdk-ui/chatbot-tool-usage), [AI Chat UX Patterns for Production Interfaces](https://www.metacto.com/blogs/ai-chat-ux-patterns-production)
- Empty states: [Empty states (Cloudscape Design System)](https://cloudscape.design/patterns/general/empty-states/), [Empty states pattern (Carbon Design System)](https://carbondesignsystem.com/patterns/empty-states-pattern/), [Empty state UX examples (Eleken)](https://www.eleken.co/blog-posts/empty-state-ux), [SaaS Empty State Design (Pixxen)](https://pixxen.com/blog/saas-empty-state-design/)
- Stale-feed UX: [Real-Time Market Data Reliability (EODHD)](https://eodhd.com/financial-academy/fundamental-analysis-examples/real-time-market-data-reliability-stale-price-detection-rest-fallback-and-websocket-recovery), [Real-Time Market Data Fails Quietly (InsightBig)](https://www.insightbig.com/post/real-time-market-data-fails-quietly-here-s-how-to-make-it-recoverable)
- AI trading copilots: [MiDash AI Trading Copilot](https://www.midash.ai/ai-overview.html), [Alphio AI](https://alphio.ai/), [LCX AI Trading](https://lcx.com/en/ai-trading), [TradingView AI Chart Copilot](https://tvremix.xyz/)

**Confidence caveats:**
- Product feature sets (LOW→MEDIUM): drawn from vendor docs and third-party guides, cross-checked across ≥2 sources per claim. Paper-trading products change; balances and order-type support should be treated as directional.
- Design conventions (MEDIUM): color semantics, treemap encoding and empty-state guidance are consistent across independent authoritative sources (Bloomberg, Finviz, NN/g, Carbon, Cloudscape).
- Recommendations (opinionated synthesis): the Reset Portfolio gap, total-return compensation, flash/cell-color separation and the low-N treemap fallback are my analysis applied to PLAN.md, not directly-cited findings. They are the highest-value items here and also the ones most worth challenging.
- **Gap:** no direct user-research or first-party complaint data. Searches for Reddit/community complaint threads returned no usable results, so "what users find broken" is inferred from product-guide framing and design literature rather than observed user reports.

---
*Feature research for: paper-trading terminal with an AI copilot*
*Researched: 2026-08-05*
