# Pitfalls Research

**Domain:** Single-container FastAPI + SSE + static-Next.js + SQLite trading workstation with LLM tool execution
**Researched:** 2026-08-05
**Confidence:** MEDIUM-HIGH (three findings verified against primary source code or this repo's own git state and marked HIGH; the rest MEDIUM from corroborated web sources)

## How to Read This

Pitfalls are ordered by expected damage, not by build order. Each carries a **Phase to address** naming the PLAN.md build-order step (section 13) the roadmap will turn into a phase.

Three findings are **verified against this repository right now**, not inferred:

| Verified fact | Evidence |
|---|---|
| `db/finally.db` (94,208 bytes) is **committed to git** at `HEAD` and is **not** gitignored — PLAN.md section 4 claims it is | `git ls-files db/` returns it; `git log -1 -- db/finally.db` → `0d1dc92`; `.gitignore:61` only has Django's `db.sqlite3` |
| `core.autocrlf = true` with **no `.gitattributes`** in the repo | `git config --get core.autocrlf` → `true`; `ls .gitattributes` → not found |
| The project root, and therefore the `db/` bind-mount source, lives inside a **OneDrive-synced folder with spaces in the path** | `C:\Users\ehasi\OneDrive\Documents\AI Coder Course\Project\finally` |

---

## Critical Pitfalls

### Pitfall 1: SQLite bind-mounted from a Windows/OneDrive path is a documented "database is locked" generator

**Confidence:** MEDIUM (corroborated: Docker's own bind-mount docs, `docker/for-win#11`, Docker forums thread 13757, current WSL2 guidance) — but the *applicability* to this repo is HIGH, since the path is verified.

**What goes wrong:**
PLAN.md section 11 specifies `docker run -v "$PWD/db:/app/db"`. On this machine `$PWD` resolves inside OneDrive. Two independent failure sources stack:

1. **Docker Desktop on Windows reaches host paths over a network-style filesystem** — SMB/CIFS historically, 9p/drvfs under the WSL2 backend. SQLite's POSIX advisory locking (`fcntl`/`flock`) is not correctly implemented across it. The result is `sqlite3.OperationalError: database is locked` or `disk I/O error` on operations that have no contention at all. This has been open since 2016 and Docker's own documentation warns against SQLite on networked bind mounts.
2. **OneDrive independently interferes.** Files On-Demand placeholders return access-denied to non-Explorer readers, OneDrive takes its own file locks that block deletes and rewrites, and — worst here — it will try to sync the live `finally.db` plus its `-wal` and `-shm` sidecars on every write. A 30-second snapshot task plus per-trade writes means near-continuous sync churn against a file SQLite expects to own exclusively.

The failure is intermittent and load-dependent, which is the worst kind. It will pass a smoke test and fail during the demo.

**Why it happens:**
The bind mount is a deliberate teaching choice ("students can see the database file, inspect it, delete it to reset" — PLAN.md section 11) and it is a good one. Nobody re-examines it when the project happens to live in OneDrive, because on a normal `C:\dev\project` path it mostly works.

**How to avoid:**
In descending order of preference:

1. **Move the project out of OneDrive.** `C:\dev\finally` or, best for Docker Desktop, inside the WSL2 filesystem (`\\wsl$\Ubuntu\home\ehasi\finally`). This also fixes pitfalls 11, 21 and 22 in one move. OneDrive has **no reliable way to exclude a subfolder by name** — this is an open, heavily-upvoted feature request, not a setting you can flip — so "just exclude `db/` and `node_modules/`" is not available.
2. **If the project must stay in OneDrive, move only the mount source out.** Keep the bind mount (preserving the teaching benefit), just not from OneDrive:
   ```powershell
   # scripts/start_windows.ps1
   $dbPath = "$env:LOCALAPPDATA\finally\db"
   New-Item -ItemType Directory -Force -Path $dbPath | Out-Null
   docker run -v "${dbPath}:/app/db" -p 8000:8000 --env-file .env finally
   ```
3. **Last resort: a Docker named volume.** Correct and fast, but loses "inspect the file" and needs `docker volume rm` to reset.

Whichever is chosen, also set `PRAGMA journal_mode=WAL` and `busy_timeout` (pitfall 5) — necessary but *not sufficient*, since WAL's shared-memory `-shm` file makes filesystems that don't support proper locking worse, not better.

**Warning signs:**
- `database is locked` or `disk I/O error` with only one process running
- The OneDrive tray icon spinning continuously while the app is idle
- `db/finally.db-wal` growing and never checkpointing
- A `finally.db` conflict copy appearing (`finally-DESKTOP-XXX.db`)
- `docker stop` then `docker start` "fixing" it for a while

**Phase to address:** Phase 0 / environment prep — **before** build step 2 writes a single line of DB code. This decision changes the start scripts and the `.env`/path handling in step 7.

---

### Pitfall 2: `db/finally.db` is committed to git — every trade produces a binary diff

**Confidence:** HIGH (verified in this repo)

**What goes wrong:**
A 94 KB SQLite binary is tracked at `HEAD`. `.gitignore` line 61 contains `db.sqlite3` (a Django default that came in with a boilerplate ignore file), not `db/finally.db`. PLAN.md section 4 asserts the opposite — "Directory exists in repo; `finally.db` is gitignored" — so nobody will check.

Once the app runs, every trade, every 30-second snapshot and every chat message rewrites the file. Consequences:

- `git status` is permanently dirty; agents and humans start committing database state alongside code
- Binary merge conflicts that cannot be resolved, only chosen
- Any clone or branch switch **overwrites the running database**, silently resetting the user's portfolio or corrupting an open connection
- With WAL enabled, `-wal`/`-shm` sidecars also appear untracked and noisy
- The committed file leaks whatever state was in it into every clone, defeating "fresh Docker volumes start with a clean, seeded database"

**Why it happens:**
The file was created during exploratory work and swept in by a broad `git add`. The plan's own claim that it is ignored suppresses the check.

**How to avoid:**
Fix it now, before build step 2 adds writers:
```bash
git rm --cached db/finally.db
printf 'db/*.db\ndb/*.db-wal\ndb/*.db-shm\n!db/.gitkeep\n' >> .gitignore
touch db/.gitkeep && git add db/.gitkeep .gitignore
```
Then add a lazy-init assertion in build step 2: on startup, if the DB file exists but has no `users_profile` table, recreate rather than assume.

**Warning signs:**
- `git status` shows `modified: db/finally.db` after using the app
- A phase commit diff contains `Binary files differ`
- Two agents working in parallel both touch `db/`

**Phase to address:** Immediately (housekeeping), and re-verified at build step 2 (database layer) and step 7 (Docker).

---

### Pitfall 3: Static mount shadowing the API — and the four related mounting traps the plan does not cover

**Confidence:** HIGH for mechanics (verified against Starlette `staticfiles.py` source)

**What goes wrong:**
PLAN.md already flags the headline case: `app.mount("/", StaticFiles(...))` registered before the `/api/*` routers matches every path, so every endpoint 404s while the UI looks fine. Starlette's router iterates `self.routes` in registration order and `Mount("/")` matches unconditionally.

The plan does **not** cover the failure *signature* or four adjacent traps:

**3a — The signature is an HTML 404, not a JSON one.** Next.js static export emits a `404.html`. Starlette's `StaticFiles` in `html=True` mode, on a miss, serves `404.html` with status 404 if it exists. So a shadowed API returns:
```
HTTP/1.1 404 Not Found
content-type: text/html; charset=utf-8
```
Not FastAPI's `{"detail":"Not Found"}`. That content-type is the fastest one-command diagnostic:
```bash
curl -sI http://localhost:8000/api/health | grep -i content-type
# text/html  -> the API is shadowed
# application/json -> routing is fine
```

**3b — `html=True` does NOT do SPA fallback.** Reading the source: on a miss it tries `404.html`, then raises `HTTPException(404)`. It never rewrites unknown paths to `index.html`, and it never probes for an implicit `.html` suffix. Combined with Next's default `trailingSlash: false` (which writes `out/about.html`, not `out/about/index.html`), **any route other than `/` will 404 on hard refresh or deep link.** For a strictly single-page app this is invisible until someone adds a second route or the E2E suite navigates directly to a path.

**3c — Directory-without-slash issues a redirect.** `lookup_path` on a directory without a trailing slash returns `RedirectResponse(path + "/")`. Harmless for `GET`, but it means a route registered as `/api/watchlist` and requested as `/api/watchlist/` gets FastAPI's own 307 `redirect_slashes` behavior — which preserves method and body, so `POST` survives, but the extra round trip shows up in Playwright request assertions and looks like a bug.

**3d — `StaticFiles` raises at import time if the directory is missing.** `StaticFiles(directory="static")` raises `RuntimeError: Directory 'static' does not exist` when the frontend has not been built. That is the *normal* state during local backend development. Backend work stops dead until someone runs `npm run build`.

**How to avoid:**
```python
# backend/app/main.py — routers first, always
app.include_router(health_router)
app.include_router(create_stream_router(price_cache))
app.include_router(portfolio_router)
app.include_router(watchlist_router)
app.include_router(chat_router)

# static LAST, and only if it exists (local dev has no build)
static_dir = Path(__file__).parent / "static"
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
else:
    logger.warning("No static/ directory; serving API only")
```
Plus:
- Set `trailingSlash: true` in `next.config.js` so the export writes `out/<route>/index.html`, which Starlette resolves without any rewrite rule. Cheap insurance even for a one-route SPA.
- Write **one test** that is impossible to fake:
  ```python
  def test_api_not_shadowed_by_static(client):
      r = client.get("/api/health")
      assert r.status_code == 200
      assert r.headers["content-type"].startswith("application/json")
  ```
  Run it against the *built container*, not just the test app — the test app usually has no `static/` and so cannot reproduce the bug.

**Warning signs:**
- The UI loads but every panel is empty and the network tab shows 404s for `/api/*`
- `/api/health` returns `text/html`
- Backend tests pass, the container fails

**Phase to address:** Build step 2 (app assembly), re-verified in step 7 (Docker) with a container-level smoke test.

---

### Pitfall 4: Float money math — the spec's REAL columns will produce dust positions and off-by-a-cent rejections

**Confidence:** HIGH (deterministic IEEE-754 behavior). **The spec does not address this at all.**

**What goes wrong:**
`quantity`, `avg_cost`, `price`, `cash_balance` and `total_value` are all SQLite `REAL` (IEEE-754 double), and PLAN.md explicitly supports fractional shares. Four concrete bugs follow:

**4a — "Sell all" leaves a dust position that can never be removed.**
```
buy 0.1 AAPL  x3   ->  quantity = 0.1 + 0.1 + 0.1 = 0.30000000000000004
sell 0.3           ->  remaining = 5.55e-17
```
`5.55e-17 != 0`, so the row is **not** deleted. PLAN.md section 7 says "a sell that takes quantity to zero deletes the row — there are no zero-quantity positions". That invariant is now broken. The positions table shows a ghost row rendering as `0.0000`, the treemap gets a zero-area invisible rectangle, and — the real damage — `DELETE /api/watchlist/{ticker}` returns **409 forever** because a position is "held". The user can neither sell it (they own 5.55e-17 shares) nor remove it from the watchlist. That is an unrecoverable UI state reachable in about four clicks.

**4b — Cash comparisons reject trades that should succeed.**
`cash_balance` accumulates rounding across every trade. After a few round trips it holds `1905.1999999999998` while the UI renders `$1905.20`. The user clicks "buy" for exactly what they see and gets:
> `Insufficient cash: need $1905.20, have $1905.20`

An error message that contradicts itself, verbatim, to the user — which PLAN.md section 8 says these messages are written to be.

**4c — `avg_cost` drift shows P&L on a position that never moved.**
`new_avg = (old_qty * old_avg + qty * price) / (old_qty + qty)` compounds error. A position bought once, with the price unchanged, reports `unrealized_pnl = -2.8e-14`. `toFixed(2)` renders that as **`-0.00`**, colored red. Small, but it is on screen in the positions table during the demo.

**4d — Sum-then-compare in the client.**
`cash + Σ(quantity × live price)` is recomputed on every SSE frame (PLAN.md section 10). Summing 10 doubles 2×/second is numerically fine, but any equality check against a server-returned `total_value` will fail.

**Why it happens:**
The stakes look like zero ("it's fake money"), and `Decimal` end-to-end feels like overengineering — which it *is*, for this project. So nothing gets done, and the middle ground is skipped.

**How to avoid — the proportionate fix, not the heavy one:**

Do **not** thread `Decimal` through the codebase. SQLite has no decimal type, JSON has no decimal type, and JavaScript has no decimal type; it would infect every layer for a simulator. Three small rules cover every case above:

```python
# backend/app/db/money.py
QTY_EPSILON = 1e-9      # below this, a position is gone
CASH_EPSILON = 0.005    # half a cent

def round_money(x: float) -> float:
    """Round to cents. Applied at every DB write of a currency value."""
    return round(x, 2)

def round_qty(x: float) -> float:
    """Round to 4dp, the precision PLAN.md section 8 already mandates for input."""
    return round(x, 4)
```

1. **Round at the write boundary.** Every value written to `cash_balance`, `avg_cost`, `price`, `total_value` goes through `round_money`; every `quantity` through `round_qty`. Reads and in-flight arithmetic stay raw. This alone kills 4b and 4c.
2. **Compare with a tolerance, never with `==` or bare `>`.**
   ```python
   if quantity > held + QTY_EPSILON:
       raise HTTPException(400, f"Insufficient shares: have {held:.4f}, tried to sell {quantity:.4f}")
   remaining = round_qty(held - quantity)
   if remaining <= QTY_EPSILON:
       delete_position(ticker)          # restores the "no zero-quantity positions" invariant
   else:
       update_position(ticker, remaining)

   if total_cost > cash + CASH_EPSILON:
       raise HTTPException(400, f"Insufficient cash: need ${total_cost:.2f}, have ${cash:.2f}")
   ```
3. **Normalize `-0` on the client.**
   ```ts
   const fmt = (n: number) => (Math.abs(n) < 0.005 ? 0 : n).toFixed(2);
   ```
   And drive the red/green class from `Math.abs(pnl) < 0.005 ? 'flat' : pnl > 0 ? 'up' : 'down'`, not from `pnl > 0`.

**Warning signs:**
- A positions row showing `0.0000` shares
- A 409 on removing a ticker the user believes they fully sold
- An "insufficient cash" message where the two numbers printed are identical
- `-0.00` anywhere in the UI
- A P&L value with more than 2 significant decimals in a JSON response

**Phase to address:** Build step 2 (database + portfolio/trade logic). The epsilon rules must exist *before* trade execution is written, not bolted on. Frontend formatting in step 4. Add unit tests for exactly the three sequences above (`0.1 × 3` then sell `0.3`; buy-max-cash twice; buy-then-sell-all-then-remove-from-watchlist).

---

### Pitfall 5: SQLite read-then-write transactions get `SQLITE_BUSY` that `busy_timeout` cannot fix

**Confidence:** MEDIUM (corroborated: SQLite locking docs, multiple independent write-ups)

**What goes wrong:**
Three writers exist by design: the request handler executing a trade, the 30-second snapshot background task, and the chat handler auto-executing LLM trades. All three read then write.

Default `busy_timeout` is **zero** — SQLite returns `SQLITE_BUSY` instantly on any contention. Setting WAL plus a timeout fixes ~99% of cases. But there is one case a timeout **cannot** fix, and it is exactly the shape of the trade endpoint:

Python's `sqlite3` opens **DEFERRED** transactions by default. A deferred transaction that starts with a `SELECT` acquires a read snapshot; when it later issues an `UPDATE`, it must *upgrade* to a write transaction. If any other connection wrote since the snapshot, SQLite returns `SQLITE_BUSY` **immediately and does not wait**, because the read is already invalidated — waiting would be pointless. `busy_timeout` is bypassed entirely.

The trade path is: read cash → read position → write position → write cash → insert trade → insert snapshot. If the 30-second snapshot task commits in that window, the trade fails with a raw 500 and the user's click does nothing.

At single-user demo scale this fires rarely — perhaps once per few hundred trades — which means it will not appear in testing and will appear during the demo.

**How to avoid:**
```python
def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def write_txn(conn):
    """Any transaction that reads then writes must take the write lock up front."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
```
- `isolation_level=None` turns off the stdlib's implicit transaction management so `BEGIN IMMEDIATE` actually takes effect.
- `busy_timeout=5000` — benchmarks show errors below 5 s and none at or above it.
- `check_same_thread=False` is required because FastAPI runs `def` (non-async) endpoints in a threadpool, so a module-level connection crosses threads. **But it removes sqlite3's own guard**, so pair it with either a `threading.Lock` around writes or, simpler and better here, one connection per request via a FastAPI dependency. One connection per request is the recommendation — it is fewer lines than a lock and it also bounds transaction lifetime.
- Keep write transactions to the minimum: the whole trade (position + cash + trade row + snapshot row) is *one* `BEGIN IMMEDIATE` block, not four.

**Warning signs:**
- Intermittent 500s from `POST /api/portfolio/trade` that never reproduce
- `sqlite3.OperationalError: database is locked` in logs at ~30-second intervals (the snapshot task's cadence is the tell)
- A `finally.db-wal` file that grows without checkpointing

**Phase to address:** Build step 2 (database layer). Write the connection factory and `write_txn` helper first; every later writer uses them.

---

### Pitfall 6: The LLM executes trades with no confirmation — five distinct ways that goes wrong

**Confidence:** MEDIUM (patterns are well-established in agentic tool-execution systems). **The spec does not address any of these.**

Auto-execution is a deliberate, correct choice for this demo (PLAN.md section 9). It is also the highest-variance surface in the project, because the failure is *visible, immediate, and irreversible within the session*.

**6a — The same trades execute twice.**
The user presses Enter, the request is slow (LLM latency), they press Enter again — or the send button fires on both `click` and form `submit`. Two `POST /api/chat` calls, two LLM responses, two identical `buy 10 NVDA`. The portfolio is now double what the user asked for and the chat shows two confirmations.

A second, subtler route: if LiteLLM is configured with `num_retries`, the *inference* is retried, not the execution — that is safe, provided execution happens strictly **after** a successful parse. It becomes unsafe the moment anyone wraps the whole handler in a retry.

*Prevention:* disable the input and send button while a request is in flight (`disabled={pending}`); handle `onSubmit` only, never both `onClick` and `onSubmit`; keep the pipeline strictly `call → parse → execute` so retries only ever re-run inference; never add retry middleware around `POST /api/chat`.

**6b — The AI trades on a question.**
"Should I sell TSLA?" / "What would happen if I bought 100 NVDA?" / "How much AAPL could I afford?" are the three most natural things a user says to a trading copilot, and a model with a `trades[]` field will fill it in for all three. The user asked a question and lost $19,000 of simulated cash.

*Prevention:* this is a prompt problem with a cheap structural backstop.
- System prompt must state the rule explicitly and give negative examples: *"Populate `trades` ONLY when the user has given an explicit instruction to trade or has agreed to a trade you proposed. If the user is asking a question, exploring a hypothetical, or asking for advice, `trades` MUST be `[]` and your reasoning goes in `message`."* Include two worked examples of question-shaped inputs returning `trades: []`.
- Add **one** server-side guard, not a confirmation dialog: reject any single LLM-originated trade whose notional exceeds a fraction of total portfolio value (50% is a reasonable line), returning the rejection as text the LLM's response carries. One rule, ~4 lines, and it converts "the AI liquidated everything" from a demo-ending event into a visible, explainable refusal. Manual trades are not subject to it — the user typed the number themselves.

**6c — The AI acts on stale portfolio context.**
Context is assembled at request start. The user may trade manually while the LLM is thinking; more commonly, the LLM emits multiple trades in one response and trades 2..n are reasoned against pre-trade cash. "Sell all your AAPL and buy NVDA with the proceeds" computes the NVDA quantity from cash that does not exist yet.

*Prevention:* execute trades **sequentially**, each re-reading server state (the trade path already does this — do not add a fast path that skips it). Collect a per-trade result and put every one, success or failure, into the response and into the `actions` JSON. **Do not** wrap the batch in a single transaction that rolls back on failure — partial success with honest reporting is correct here, and a rollback would leave the `portfolio_snapshots` rows inconsistent with `trades`.

**6d — "Sell all" plus float dust.**
The LLM reads `quantity: 0.30000000000000004` from context and, being a language model, emits `0.3`. Sell 0.3 of 0.30000000000000004 → the dust position from pitfall 4a, now created by the AI rather than the user. Present `quantity` **already rounded** in the LLM context (`round_qty`), and rely on the epsilon deletion rule.

**6e — Hallucinated tickers always "work", which is worse than failing.**
The simulator accepts unknown tickers by design and synthesizes a deterministic seed price. So when the model hallucinates `APPL` (a typo for AAPL) or invents a company, the ticker is added, gets a plausible price, and can be traded. Nothing errors. `^[A-Z]{1,5}$` is a *format* check, not a *existence* check.

*Prevention:* do not "fix" this — it is the documented design (PLAN.md section 6) and it is what keeps the watchlist demo from dead-ending. But do not present it as validation either, and note it in the demo script. If a real-symbol check is ever wanted, it belongs on the Massive path only, where a symbol lookup exists.

**Warning signs:**
- Two identical assistant messages in `chat_messages` with adjacent `created_at`
- A position size that is exactly 2× what the chat transcript requested
- A trade executed in a turn whose user message ends in a question mark
- `cash_balance` at or near zero after one chat turn
- Watchlist entries that are not real companies

**Phase to address:** Build step 6 (chat + LLM). 6a's frontend half belongs in step 6's chat panel work. The notional cap in 6b and sequential execution in 6c belong in the chat router, reusing step 2's trade function unchanged.

---

### Pitfall 7: `gpt-oss-120b` structured output is not guaranteed — and the right fix is routing config, not defensive parsing

**Confidence:** MEDIUM (corroborated: OpenRouter structured-outputs docs; Groq community report of `response_format` being ignored by `openai/gpt-oss-120b`; `lmstudio-ai/lmstudio-bug-tracker#1105`; Harmony leakage reports in `NVIDIA/TensorRT-LLM#9256`, `sgl-project/sglang#10061`, `vllm-project/vllm#37030`; `openai/harmony#80`)

**What goes wrong:**
OpenRouter's `response_format: {type: "json_schema", ...}` is honored **only by providers that implement it**. Enforcement varies: some providers guarantee schema-conforming output, some translate the schema into their own format, and some treat it as a strong hint. If OpenRouter routes to a fallback endpoint that does not support it, the parameter is **silently ignored** and prose comes back.

`gpt-oss-120b` specifically has confirmed reports of `json_schema` with `strict: true` being ignored and free-form text returned. The model also uses the **Harmony** format with `<|channel|>` / `<|message|>` control tokens and `analysis` / `commentary` / `final` channels; multiple serving stacks have leaked those control tokens or reasoning content into the assistant `content` field. LiteLLM surfaces the extra `reasoning_content` and `provider_specific_fields` keys, and strict parsers choke on them.

Observed failure shapes, roughly by frequency:
1. Valid JSON wrapped in ` ```json ... ``` ` fences
2. `content` empty because the answer landed in `reasoning_content`
3. Prose preamble ("Sure! Here's the JSON:") before the object
4. Harmony control tokens embedded in `content`
5. A key omitted entirely (`trades` missing rather than `[]`) — PLAN.md section 9 already anticipates this by requiring all three fields
6. Extra keys the schema did not ask for
7. A refusal in natural language with no JSON at all

**How to avoid:**

**First, fix routing — this is where most of the value is, and it is configuration, not code:**
```python
response = litellm.completion(
    model="openrouter/openai/gpt-oss-120b",
    messages=messages,
    response_format={
        "type": "json_schema",
        "json_schema": {"name": "finally_response", "strict": True, "schema": SCHEMA},
    },
    extra_body={
        "provider": {
            "order": ["Cerebras"],
            "require_parameters": True,   # refuse to route anywhere that cannot honor response_format
            "allow_fallbacks": False,
        }
    },
)
```
`require_parameters: True` is the single highest-leverage line: it makes OpenRouter refuse an endpoint that would silently drop the schema, converting an invisible correctness failure into a loud routing error.

**Second, the minimum genuinely-necessary parsing.** The project style says do not program defensively — so here is the precise floor, and what is over the line.

*Necessary (about 12 lines total):*
```python
FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)

class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")   # kills failure 6 for free
    message: str
    trades: list[Trade] = []                    # kills failure 5 for free
    watchlist_changes: list[WatchlistChange] = []

def parse(raw: str) -> ChatResponse:
    try:
        return ChatResponse.model_validate_json(FENCE.sub("", raw).strip())
    except (ValidationError, ValueError):
        # Failures 3, 4, 7: no usable JSON. Not an error the user should see as a 500.
        return ChatResponse(message=raw.strip()[:500])
```
That is it. Three mechanisms: strip fences (one regex), `extra="ignore"` plus field defaults (free, in the model definition), one `except` returning the degraded-but-valid shape. The fallback returns the model's prose as `message` with empty action arrays — which is exactly the shape PLAN.md already specifies for the no-API-key case, so no new response variant is introduced.

*Over the line — do not build these:*
- A retry-with-corrective-prompt loop
- A JSON-repair library
- Regex extraction of trade objects out of prose
- Per-field type coercion beyond what Pydantic does
- A second LLM call to fix the first

One extra line is worth it because it is cheap and the symptom is otherwise baffling: if `content` is empty, check `reasoning_content` before falling back.

**Warning signs:**
- `message` in the UI containing a literal ` ``` ` or `<|channel|>`
- The assistant replying with a JSON blob as visible text
- `trades` never populating even when the user clearly instructed a trade (schema silently ignored → the model wrote prose)
- Intermittent behavior differences between runs at the same prompt (fallback provider routing)

**Phase to address:** Build step 6 (LLM integration). Validate `require_parameters` behavior in a spike *before* writing the chat router — if Cerebras + `gpt-oss-120b` will not honor `json_schema`, that is a model-selection decision, not a parsing problem, and it is much cheaper to discover early.

---

### Pitfall 8: React StrictMode double-mounts the EventSource, and HTTP/1.1 gives you only six connections

**Confidence:** MEDIUM (corroborated: React docs on StrictMode, MDN EventSource, textslashplain HTTP/1.1 EventSource analysis, Chrome/Firefox WONTFIX on the connection cap)

**What goes wrong:**
React StrictMode (18 and 19) mounts → unmounts → remounts every component in development. An effect that constructs an `EventSource` without returning a cleanup opens **two** connections per page load. Each Fast Refresh adds more.

That would be a dev-only annoyance except for the connection cap: **over HTTP/1.1 a browser allows six concurrent connections per origin**, shared with *all* other requests to that origin. Chrome and Firefox have marked this WONTFIX. Uvicorn serves HTTP/1.1 only — there is no HTTP/2 in this container — and the app is single-origin by design, so `/api/portfolio`, `/api/watchlist`, `/api/chat` and every static asset compete for the same six slots as the SSE stream.

The failure cascade: leaked streams accumulate → the pool saturates → `fetch('/api/portfolio')` after a trade **hangs indefinitely** with no error. The UI freezes with a green connection dot, because the SSE stream is still fine. This is close to undiagnosable from symptoms.

It also multiplies across tabs. Two tabs of the app plus one leak is already 3+ of 6.

Two more related behaviors:
- **Backgrounded tabs are throttled**, and long-lived requests may be delayed or terminated. On return to the foreground the prices jump. The 15s heartbeat plus the "silent for >30s ⇒ yellow" rule in PLAN.md section 2 handles this correctly *if* the frontend uses `document.visibilitychange` to avoid flashing yellow on every tab switch.
- **Reconnect storms.** The stream opens with `retry: 1000`. If the backend errors immediately on connect (e.g., the market task crashed), EventSource reconnects every second forever, generating one log line per second and never surfacing an error to the user.

**How to avoid:**
```tsx
// One EventSource for the whole app. Mount it once, high in the tree.
export function usePriceStream() {
  const [prices, setPrices] = useState<Record<string, PriceUpdate>>({});
  const [state, setState] = useState<'open' | 'connecting' | 'closed'>('connecting');
  const lastMsg = useRef(Date.now());

  useEffect(() => {
    const es = new EventSource('/api/stream/prices');
    es.onopen = () => { lastMsg.current = Date.now(); setState('open'); };
    es.onmessage = (e) => {
      lastMsg.current = Date.now();
      setPrices(JSON.parse(e.data));   // functional/replace form: no dep on `prices`
    };
    es.onerror = () => {
      setState(es.readyState === EventSource.CLOSED ? 'closed' : 'connecting');
    };
    return () => es.close();           // <- the whole pitfall is this line
  }, []);                              // <- empty deps; never re-create the stream
  // ...
}
```
Non-negotiables:
- **Return `() => es.close()`.** StrictMode's double-mount exists to surface exactly this.
- **Empty dependency array**, and never reference changing state inside the handlers — use `useRef` or the functional `setState` form. An effect that depends on `prices` and also sets `prices` tears down and reopens the connection twice per second, which is the same leak at 100× the rate.
- **Exactly one `EventSource` in the app.** Do not let the watchlist panel, the chart and the header each open their own — that is 3 of the 6 slots before anything goes wrong. One stream, distributed by context or a store.
- Verify with the backend's own logging: `stream.py` already logs `SSE client connected: %s`. **One page load must produce exactly one line in production and exactly two in StrictMode dev.** Three or more means a leak.
- Add a `/api/health` check to the connection-dot logic rather than relying on the stream alone, so a reconnect storm is visible.

**Warning signs:**
- Two `SSE client connected` log lines per page load in a production build
- Price flash animations firing twice per tick
- `fetch` calls that hang with no network error after the app has been open a while
- The Chrome network tab showing multiple `prices` requests in `pending`

**Phase to address:** Build step 4 (frontend shell / SSE wiring). Verify at step 8 by asserting the backend log line count.

---

### Pitfall 9: Playwright's `page.route()` does not reliably intercept EventSource — the plan's SSE-resilience test will not work as written

**Confidence:** MEDIUM (corroborated: `microsoft/playwright#15353`, multiple reports of `route.fulfill` producing *"EventSource's response has a Content-Type specifying an unsupported type: -. Aborting the connection"*)

**What goes wrong:**
PLAN.md section 12 specifies: *"SSE resilience: block the `/api/stream/prices` route with `page.route()`, assert the status dot leaves green, unblock, assert it returns to green."*

`page.route()` is documented as not reliably intercepting `EventSource` requests. `eventsource` is a valid `resourceType` filter, but interception of a long-lived stream is not supported, and `route.abort()` on an **already-open** stream does not tear it down. The test will either fail to fire at all, or fire on the initial request only and then not on the automatic reconnects — so "unblock and assert it returns to green" silently passes for the wrong reason.

This is a spec bug, not an implementation bug, and it will burn an afternoon during step 8 if it is not flagged during roadmapping.

**How to avoid:**
Use browser-context offline mode, which kills the transport *and* the reconnect attempts, and exercises the real `EventSource` retry path rather than a mock:
```ts
test('connection dot reflects stream health', async ({ page, context }) => {
  await page.goto('/');
  const dot = page.getByTestId('conn-dot');
  await expect(dot).toHaveAttribute('data-state', 'open');

  await context.setOffline(true);
  await expect(dot).not.toHaveAttribute('data-state', 'open', { timeout: 40_000 });

  await context.setOffline(false);
  await expect(dot).toHaveAttribute('data-state', 'open', { timeout: 40_000 });
});
```
Notes: the timeout must exceed the frontend's own 30-second silence threshold (PLAN.md section 2), so a 40 s budget, not the 5 s default. If `page.route` interception *is* wanted, register it on the **context** before `page.goto` so the very first request is caught — but verify it in a spike before writing the assertion, and do not rely on it for the recovery half of the test.

Also required: the connection state must be exposed as a **stable attribute** (`data-state="open|connecting|closed"`), not inferred from a CSS colour class. Asserting on a colour is brittle and unreadable in failure output.

**Warning signs:**
- The SSE-resilience test passes on the first run and never fails, even when the stream is deliberately broken
- Console output showing `EventSource's response has a Content-Type specifying an unsupported type`
- The test passing locally against `next dev` but not against the container

**Phase to address:** Build step 8 (E2E). Flag during roadmapping so the phase plan does not copy PLAN.md's wording verbatim. Also update PLAN.md section 12 once the approach is settled.

---

### Pitfall 10: `uvicorn --workers N` gives every worker its own price universe

**Confidence:** HIGH (follows directly from the module's in-process, in-memory design, verified in `backend/app/market/`)

**What goes wrong:**
`PriceCache` is an in-memory, in-process object and the market data source is an in-process background task. With more than one uvicorn worker:

- Each worker runs **its own simulator** with its own GBM random walk. Worker A's AAPL is $190.50; worker B's is $187.20.
- A browser's SSE stream is pinned to one worker; its `POST /api/portfolio/trade` load-balances to another. The fill price the user receives has no relationship to the price they saw stream in — and PLAN.md's own rule is *"the client's displayed price is advisory; the server fills at whatever is in the price cache when the request lands"*. Both statements are true and the result is nonsense.
- Each worker runs **its own 30-second snapshot task**, so `portfolio_snapshots` accumulates N rows per interval, the "skip if unchanged" optimization stops working, and SQLite write contention multiplies (feeding pitfall 5).
- `open_price` — the session baseline the whole change-% column depends on — is pinned per worker, so the same ticker shows different change percentages depending on which worker answered.

**Why it happens:**
`--workers 4` is the reflexive "production" setting, and it is the correct default for a stateless FastAPI app. This app is not stateless. Nothing in the code stops it, and the symptom (prices that disagree with fills) reads like a trading-logic bug rather than a deployment bug.

**How to avoid:**
- Single worker, explicitly and with a comment explaining why:
  ```dockerfile
  CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
  ```
- Do not add Gunicorn with uvicorn workers.
- Put the constraint in the module docstring of `main.py` where someone tuning performance will read it.
- Consider a startup assertion if the environment suggests multiple workers.

**Warning signs:**
- `fill_price` in a trade response differing from the streamed price by more than a tick
- Duplicate `portfolio_snapshots` rows with near-identical `recorded_at`
- Change-% flipping between two values on refresh

**Phase to address:** Build step 7 (Docker). Note it in step 2 as a constraint on the snapshot task's design.

---

### Pitfall 11: `core.autocrlf=true` with no `.gitattributes` will break `start_mac.sh` and any container entrypoint

**Confidence:** HIGH (repo state verified; CRLF-in-container behavior is deterministic)

**What goes wrong:**
`core.autocrlf` is `true` and there is no `.gitattributes`. Every text file this repo produces gets CRLF on checkout. PLAN.md section 11 calls for `scripts/start_mac.sh` and `scripts/stop_mac.sh`, and a Dockerfile that may gain an entrypoint script. In a Linux container or on macOS these fail with:
```
/bin/sh^M: bad interpreter: No such file or directory
$'\r': command not found
```
The Windows developer never sees it. It fails for the course's macOS/Linux students on first run — the exact audience the scripts exist for.

The same mechanism has a second victim: **`.env` saved with CRLF.** Each value picks up a trailing `\r`, so `OPENROUTER_API_KEY` becomes `sk-or-...\r` and OpenRouter returns a 401 with no hint as to why. Docker's `--env-file` parser has improved here, but the backend also reads `../.env` directly in local development, where whatever reader is used may not strip it.

**How to avoid:**
Commit a `.gitattributes` **before** any shell script is written:
```gitattributes
* text=auto eol=lf

*.sh          text eol=lf
Dockerfile    text eol=lf
*.dockerfile  text eol=lf
.env.example  text eol=lf

*.ps1 text eol=crlf
*.bat text eol=crlf
*.cmd text eol=crlf

*.db   binary
*.png  binary
*.ico  binary
```
`.gitattributes` overrides per-user `core.autocrlf` and travels with the repo, which per-machine config does not. Then renormalize: `git add --renormalize . && git commit`.

Also note the related trap on the other side: Docker's `--env-file` does **not** do shell parsing. `KEY="value"` yields a value that literally includes the quotes, there is no variable interpolation, and `export KEY=...` is not understood. Write `.env` and `.env.example` with bare, unquoted values.

**Warning signs:**
- A macOS/Linux user reports `bad interpreter` or `\r: command not found`
- A 401 from OpenRouter with a key that is visibly correct
- `git diff` showing whole-file changes on a file nobody edited

**Phase to address:** Immediately (housekeeping), and enforced in step 7 when the scripts are written.

---

### Pitfall 12: Recharts re-renders every panel twice per second

**Confidence:** MEDIUM (corroborated: Recharts performance guide, `recharts#945`, `recharts#2251`, Treemap source read directly)

**What goes wrong:**
The SSE stream emits one event carrying all tickers roughly twice per second. If that lands in state held above the chart panels, **every** Recharts chart re-renders 2×/s: the main line chart, ten sparklines, the treemap and the P&L chart. Each rebuilds its SVG and each `ResponsiveContainer` carries a `ResizeObserver`.

Worse, Recharts animates by default. Setting `isAnimationActive={false}` alone is **not sufficient** — `recharts#945` documents that dots still render after the default 1500 ms delay unless `animationDuration={0}` is also set. At a 500 ms tick interval, animations from tick *n* are still running when tick *n+2* arrives.

Two accumulation bugs compound it:
- **Unbounded history.** Appending every SSE frame to a chart series grows at 2 points/second — 7,200 points per ticker per hour. A long demo session degrades continuously and then jank turns into freeze.
- **The P&L chart is not a price chart.** `portfolio_snapshots` arrive every 30 s. Appending a point per SSE frame to that series makes it grow 60× faster than intended and destroys the shape of the line.

**How to avoid:**
```tsx
// Sparklines: 10 of them, re-rendering 2/s. No ResponsiveContainer, no animation, no dots.
const Sparkline = memo(function Sparkline({ data }: { data: number[] }) {
  const series = useMemo(() => data.map((v, i) => ({ i, v })), [data]);
  return (
    <LineChart width={96} height={28} data={series}>
      <Line dataKey="v" dot={false} isAnimationActive={false} animationDuration={0}
            stroke="#209dd7" strokeWidth={1.5} />
    </LineChart>
  );
});
```
Rules:
- `isAnimationActive={false}` **and** `animationDuration={0}` on every chart.
- `dot={false}` on all line series; dots are the dominant cost at 60+ points.
- Fixed `width`/`height` for sparklines. Ten `ResizeObserver`s in a scrolling table earn nothing.
- `React.memo` every chart wrapper, and `useMemo` the data array and **any object or function prop** — a fresh object literal on each render defeats `memo` entirely.
- **Cap history with a ring buffer** (~300 points for the main chart) rather than appending forever.
- **P&L series comes from `/api/portfolio/history` only.** Render the live value as a single trailing point that is *replaced*, not appended.
- Consider throttling the state that feeds charts to ~4 Hz even though the stream is 2 Hz, so a future faster stream does not change the render profile. The watchlist price cells should still update at full rate — the flash animation is the point.

**Warning signs:**
- Console warning `The width(0) and height(0) of chart should be greater than 0`
- Visible jank while the chat panel is open
- Chrome DevTools performance profile dominated by `recharts` render frames
- Memory growth over a long session

**Phase to address:** Build step 5 (charts). The stream-state architecture that determines whether this is even possible is decided in step 4 — flag it there.

---

## Moderate Pitfalls

### Pitfall 13: Recharts `ResponsiveContainer` collapses to zero height inside CSS grid/flex

**What goes wrong:** `ResponsiveContainer height="100%"` computes 100% of the parent box. In a `1fr` grid row or a flex child whose height is content-derived, the parent's height depends on the chart and the chart's height depends on the parent — circular, resolves to 0, chart disappears. Confirmed browser divergence: Chrome renders `flex-grow: 1` correctly where Safari and Firefox do not (`recharts#2251`). A Bloomberg-style dense grid layout is precisely the shape that triggers this.

**How to avoid:** Give the chart's immediate wrapper an explicit height (or `min-height`) in pixels, and add `min-h-0` to every flex/grid ancestor between the panel and the chart (the default `min-height: auto` on flex items is what prevents collapse). In Tailwind: `<div className="flex-1 min-h-0"><div className="h-full min-h-[240px]">…</div></div>`. Verify in Firefox, not just Chrome.

**Warning signs:** Chart panel renders as an empty box; console shows the `width(0) and height(0)` warning; it works at one browser zoom level and not another.

**Phase to address:** Build step 5 (charts), with a layout check in step 4.

---

### Pitfall 14: Treemap silently clamps zero, negative and NaN values to zero area

**Confidence:** HIGH (read directly from `recharts/src/chart/Treemap.tsx`)

**What goes wrong:** `computeNode` does `nodeValue = isNan(numericValue) || numericValue <= 0 ? 0 : numericValue`, and `getAreaOfChildren` applies the same clamp to computed area. Nothing throws — the node simply becomes an invisible zero-area rectangle. Three concrete consequences here:

- **Sizing by P&L instead of market value** puts every losing position at zero area. The heatmap shows only winners. PLAN.md is right that it should be *sized by weight, coloured by P&L* — but that ordering has to be honoured deliberately, because "size by P&L" is the intuitive reading of "heatmap".
- **A float-dust position** (pitfall 4a) has a market value that rounds to zero and vanishes from the treemap while still appearing in the positions table. The two panels disagree.
- **Empty data renders nothing.** The layout is guarded by `if (children && children.length)`. On first launch — $10,000 cash, zero positions, which is *exactly* the state PLAN.md section 2 describes for the first-run experience — the heatmap panel is a blank rectangle. This is a first-impression bug in a project whose stated value is visual polish.

**How to avoid:** Size by `market_value` (always positive for a held position), colour by `unrealized_pnl_percent`. Render an explicit empty state when `positions.length === 0` ("No positions — buy something to populate the heatmap") rather than mounting a Treemap with `data={[]}`. Filter out positions below the quantity epsilon before building treemap data. For the single-position case, the one rectangle fills the panel and custom label content will overflow — measure against the node's `width`/`height` and hide the label below a threshold.

**Phase to address:** Build step 5 (charts).

---

### Pitfall 15: Compression or buffering middleware silently breaks SSE

**What goes wrong:** Adding `GZipMiddleware` (or any middleware that buffers the response body) to the FastAPI app compresses the streaming response, holding frames until a compression block fills. Prices arrive in bursts or stop entirely. The connection dot stays green because the heartbeat is also buffered — everything looks connected and nothing updates. The existing `X-Accel-Buffering: no` header only speaks to nginx and does nothing about in-process middleware.

**How to avoid:** No global compression middleware. If compression is ever wanted for the static bundle, apply it only to the static mount, never to `/api/stream/*`. Note in `main.py` that the SSE route must not be wrapped. Similarly, any middleware that reads `response.body` (some logging middleware does) will consume the stream.

**Warning signs:** Prices arrive in clumps of many at once, or the stream stops after the first frame while the connection stays open.

**Phase to address:** Build step 2 (app assembly).

---

### Pitfall 16: The watchlist DB and the market source's ticker set drift apart

**What goes wrong:** `POST /api/watchlist` writes a row and calls `market_source.add_ticker()`. If either half fails — a duplicate-key error after the source was updated, or a source error after the row was inserted — the two disagree. A ticker in the DB but not the source shows a permanent `—` for price and an empty sparkline; a ticker in the source but not the DB streams a price nobody displays and adds noise to the correlation matrix. `DELETE` has the mirror problem. Restarting the app re-seeds the source from the DB, so the drift "fixes itself" on restart, which makes it maddening to reproduce.

**How to avoid:** DB write first, then source call; if the source call raises, roll back the DB row in the same handler. On startup, drive `market_source.start(tickers)` from the DB watchlist as the single source of truth (this also makes restart the recovery path). Add `/api/health`'s `tickers_cached` to the reconciliation check — if it disagrees with the watchlist count, something drifted, and the health endpoint already carries the number.

**Phase to address:** Build step 3 (watchlist API).

---

### Pitfall 17: `uv sync --frozen` will ship a container without `litellm`

**Confidence:** HIGH for the trigger (PROJECT.md records `litellm` present in the venv but absent from `pyproject.toml` and `uv.lock`; confirmed absent from `backend/pyproject.toml` dependencies)

**What goes wrong:** `--frozen` installs from `uv.lock` **without checking it against `pyproject.toml`**. `litellm` is currently in the local venv only. Local development works. The container builds cleanly. Then `POST /api/chat` raises `ModuleNotFoundError: No module named 'litellm'` at runtime, inside the container, only on the one endpoint nobody smoke-tests because it needs an API key.

The mirror failure is `--locked`, which *does* verify and fails the build with *"The lockfile at `uv.lock` needs to be updated"* — a much better failure, but it will surprise anyone who added a dependency and forgot to re-lock. (The two flags are mutually exclusive.)

**How to avoid:**
- `cd backend && uv add litellm` **now**, and commit the updated `uv.lock`. Never `uv pip install` into the venv for a dependency the app needs.
- Add `uv lock --check` to whatever passes for CI, or run it as a pre-Docker step, so drift fails fast and locally.
- Keep `--frozen` in the Dockerfile (it is faster and PLAN.md specifies it), but pair it with a container smoke test that imports the chat module.
- Note: dev tools are declared under `[project.optional-dependencies]` (an *extra*), not `[dependency-groups]`. Extras are not installed unless requested, so `--no-dev` is effectively a no-op here — harmless, but do not rely on it to exclude pytest/ruff. *(MEDIUM confidence — verify against the uv version pinned in the Dockerfile.)*
- Also relax `massive==2.2.0` to `>=2.2.0,<3` as CONCERNS.md recommends: an exact pin on a required dependency means a yanked release blocks every build, including simulator-only development.

**Warning signs:** `ModuleNotFoundError` that only reproduces in Docker; `uv.lock` unchanged in a commit that changed `pyproject.toml`.

**Phase to address:** Immediately (`uv add litellm`), enforced at step 7 (Docker).

---

### Pitfall 18: The Next.js export lands at the wrong path and the app serves a blank page

**What goes wrong:** `output: 'export'` writes to `frontend/out/`. The Dockerfile must copy that into whatever directory `StaticFiles` is pointed at. Off-by-one-directory here produces a distinctive failure: `index.html` is found and served, then every `/_next/static/chunks/*.js` returns 404 and the page renders **blank white with no error**, because React never boots. The server log shows 200 for `/` and 404s for `/_next/*`.

`basePath` and `assetPrefix` cause the same symptom from a different direction: any non-empty value rewrites asset URLs to a prefix the FastAPI mount does not serve.

**How to avoid:**
```dockerfile
COPY --from=frontend /build/frontend/out/ /app/app/static/
```
Keep `basePath` and `assetPrefix` unset. Add a build-time assertion (`RUN test -f /app/app/static/index.html && test -d /app/app/static/_next`) so a path mistake fails the build rather than the demo. Set `trailingSlash: true` (pitfall 3b). Smoke test with `curl -sf http://localhost:8000/_next/` rather than only checking that `/` returns 200.

**Phase to address:** Build step 7 (Docker).

---

### Pitfall 19: E2E tests mutate a persistent database, so the second run fails

**What goes wrong:** The bind-mounted SQLite file persists across container restarts by design. Playwright tests that buy shares change state permanently. "Buy 10 AAPL, assert position is 10" passes once and fails on every subsequent run showing 20, 30, 40. Test order becomes load-bearing. Someone "fixes" it by making assertions looser until the suite proves nothing.

**How to avoid:** Two complementary moves.
1. **Reset in `globalSetup`:** stop the container, delete `db/finally.db` (plus `-wal`/`-shm`), start the container, poll `/api/health` until it returns 200 with a non-zero `tickers_cached`. This also gives the suite the "fresh start: default watchlist, $10k balance" scenario PLAN.md section 12 requires — which *only* holds on a clean DB.
2. **Write delta assertions anyway.** Capture cash before, execute, assert `cashAfter ≈ cashBefore - fillPrice * qty` within a cent. Robust to leftover state and to the float dust in pitfall 4.

Also: never assert on the absolute `total_value`, which moves twice a second.

**Warning signs:** The suite passes on CI's fresh container and fails locally on the second run; a test that only passes when run alone.

**Phase to address:** Build step 8 (E2E).

---

### Pitfall 20: Asserting on a live-updating UI

**What goes wrong:** `expect(price).toHaveText('190.50')` cannot pass reliably against a value that changes every 500 ms. The same applies to `toHaveScreenshot()` on any panel containing prices — it will never match. The price-flash class is added and removed within ~500 ms, so `toHaveClass(/flash-up/)` is a coin flip even with auto-retry, because the retry may land in the gap between flashes.

**How to avoid:**
- Assert on **shape**, not value: `await expect(cell).toHaveText(/^\$?\d{1,5}\.\d{2}$/)`.
- Assert on **relationships** with tolerance: cash decreased by roughly `fill_price × qty`.
- Assert on **specific returned values**: capture `fill_price` from the trade confirmation the UI displays and assert against that exact number, which does not move.
- For the flash: expose a **persistent** `data-direction="up|down|flat"` attribute on the row (the direction is already in the SSE payload) and assert on that. The transient CSS class stays purely presentational. This is the single highest-value testability affordance to build in step 4.
- Mask live regions in any visual regression: `toHaveScreenshot({ mask: [page.locator('[data-testid="price"]')] })`.
- Use `expect.poll` / web-first assertions, never `waitForTimeout`.

**Phase to address:** Build step 8 (E2E), with the `data-*` hooks added in steps 4 and 5.

---

### Pitfall 21: OneDrive plus `node_modules` plus a long path

**Confidence:** MEDIUM (corroborated: pnpm#7592, multiple developer write-ups, Microsoft Q&A confirming no subfolder-exclusion feature)

**What goes wrong:** `npm ci` in `frontend/` creates tens of thousands of files inside a OneDrive-synced tree. OneDrive attempts to sync all of them, holds locks that surface as `EPERM` / `EBUSY` on delete or rewrite, and Files On-Demand can evict them later so a `npm run build` weeks from now stalls re-downloading. There is **no way to exclude a subfolder by name** in OneDrive — the workarounds are "move the project" or "mark always-keep-on-device", and only the first is reliable.

Path length compounds it. The prefix `C:\Users\ehasi\OneDrive\Documents\AI Coder Course\Project\finally\frontend\node_modules\` is already ~95 characters before any package nesting; the Windows `MAX_PATH` limit is 260 unless long paths are explicitly enabled.

And the path contains **spaces** (`AI Coder Course`), which breaks naive scripts and has a documented interaction with Docker Desktop's 9p mount handling.

**How to avoid:** Move the project out of OneDrive — this is the same fix as pitfall 1 and resolves both. If that is refused: `git config --global core.longpaths true`, enable Win32 long paths in Group Policy/registry, mark the project folder "Always keep on this device", and quote every path in every script. Add `node_modules/`, `.venv/`, `__pycache__/` and `db/*.db*` to `.gitignore` regardless (they should not be tracked either way).

**Phase to address:** Phase 0 / environment prep, before the frontend phase (step 4) creates `node_modules`.

---

### Pitfall 22: PowerShell start/stop script quirks

**What goes wrong:** Four distinct traps in `scripts/start_windows.ps1`:
- **Execution policy.** A default `Restricted` policy refuses to run `.ps1` at all; `RemoteSigned` blocks files marked as downloaded. The user sees a red wall of text on first run of the thing meant to be the one-command start.
- **`$PWD` is a `PathInfo` object,** not a string. `"-v $PWD/db:/app/db"` interpolates via `ToString()` and produces mixed separators; with spaces in the path the argument must be quoted as a single unit.
- **Native command failures do not stop the script.** `docker run` failing leaves `$?` false but execution continues to "open your browser", so the user gets a browser pointed at nothing.
- **Idempotency.** PLAN.md requires the scripts be safe to run repeatedly. `docker run` with a fixed `--name` fails on the second invocation with a name conflict.

**How to avoid:**
```powershell
$ErrorActionPreference = 'Stop'
$dbPath = (New-Item -ItemType Directory -Force -Path "$PSScriptRoot\..\db").FullName

docker rm -f finally 2>$null | Out-Null      # idempotent
docker run -d --name finally `
  -v "${dbPath}:/app/db" -p 8000:8000 --env-file "$PSScriptRoot\..\.env" finally
if ($LASTEXITCODE -ne 0) { throw "docker run failed" }
```
Document the invocation as `powershell -ExecutionPolicy Bypass -File scripts\start_windows.ps1` in the README. Use `$PSScriptRoot`-relative paths so the script works from any working directory. Check `$LASTEXITCODE` after every native command — `$ErrorActionPreference` alone does not catch native exit codes in Windows PowerShell 5.1.

**Phase to address:** Build step 7 (Docker and scripts).

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|---|---|---|---|
| Skip the float-epsilon rules, "it's fake money" | Saves ~20 lines in step 2 | Unremovable dust positions and self-contradicting error messages; retrofit touches every trade path and both frontend tables | Never — the fix is 20 lines and the bug is user-visible |
| One module-level SQLite connection with `check_same_thread=False` | Simplest possible DB layer | Needs a manual lock the moment two writers exist; per-request connections are *fewer* lines | Never — per-request dependency is simpler, not harder |
| Ship without `.gitattributes`, fix line endings when someone complains | Zero work now | The complainant is a macOS student on day one of the course | Never — it is a 12-line file |
| Chat state held in the top-level component alongside price state | One `useState`, no store | Every chat keystroke re-renders every chart at 2 Hz; retrofit means restructuring the tree | Acceptable only if chat state is genuinely isolated in its own subtree from the start |
| Appending SSE frames to chart series without a cap | Trivially correct on a 2-minute test | Unbounded memory, degrading frame rate over a demo session | Acceptable for a spike; never in step 5 |
| No `require_parameters` on the OpenRouter call | One less config key | Silent, intermittent, unreproducible schema failures that look like model quality problems | Never — it is one key |
| Retry the whole `POST /api/chat` on failure | Feels robust | Duplicate trade execution — the worst bug in the project | Never. Retry inference only, execute once after parse |
| Leave `db/finally.db` tracked | Nothing to do | Binary conflicts, state leaking into clones, overwritten live DB on branch switch | Never |
| Ship with the project in OneDrive | Avoids a disruptive move | Intermittent SQLite corruption and `npm` lock errors with no clear cause | Only if the DB bind-mount source is relocated outside OneDrive |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|---|---|---|
| OpenRouter / LiteLLM | Sending `response_format` and assuming it is honored | `extra_body={"provider": {"require_parameters": True, "order": ["Cerebras"], "allow_fallbacks": False}}` plus `strict: true` |
| OpenRouter / LiteLLM | Parsing `message.content` only | Fences stripped; if `content` is empty, check `reasoning_content` — `gpt-oss` splits channels |
| OpenRouter / LiteLLM | Missing key raises; app 500s | Pydantic model with `extra="ignore"` and `= []` defaults; one `except` returning `{message, [], []}` |
| OpenRouter / LiteLLM | Missing `OPENROUTER_API_KEY` fails startup | PLAN.md is explicit: normal-shaped response explaining the key is absent; never raise, never fail startup |
| SQLite | Default DEFERRED transactions on read-then-write | `BEGIN IMMEDIATE` for the trade path; `busy_timeout` does not cover the upgrade case |
| SQLite | WAL enabled, sidecars untracked and unignored | Ignore `*.db-wal` and `*.db-shm`; do not commit any of them |
| SQLite ↔ Docker | Bind mount from a Windows/OneDrive path | Mount from a local non-synced path, or use a named volume |
| Browser ↔ SSE | One `EventSource` per component | Exactly one per app, distributed via context/store; HTTP/1.1 gives you six slots total |
| Browser ↔ SSE | Effect that depends on the state it sets | Empty dependency array, `useRef`/functional `setState`, always `return () => es.close()` |
| FastAPI ↔ StaticFiles | Mount before routers | Routers first, static last, and only mount if the directory exists |
| Next export ↔ StaticFiles | Default `trailingSlash: false` | `trailingSlash: true` so every route is `dir/index.html` |
| Playwright ↔ SSE | `page.route()` to block the stream | `context.setOffline(true)`; `page.route` does not reliably intercept EventSource |
| Massive API | Assuming prices move | Off-hours quotes are flat by design (PLAN.md section 6). Simulator is the demo default |
| uv ↔ Docker | `uv pip install` into the venv for a real dependency | `uv add`, commit `uv.lock`, and gate on `uv lock --check` |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|---|---|---|---|
| Every chart re-renders on every SSE frame | UI jank, fan noise, laggy chat typing | `memo` + `useMemo`, `isAnimationActive={false}` **and** `animationDuration={0}`, fixed-size sparklines | ~4 chart panels at 2 Hz — i.e. immediately, at the spec'd design |
| Unbounded chart history from the stream | Slow degradation, growing memory | Ring buffer, ~300 points | ~20 minutes of continuous use |
| Appending SSE frames to the P&L series | P&L line shape is wrong; series grows 60× intended | P&L series comes from `/api/portfolio/history` only; live value replaces the trailing point | Immediately |
| Leaked EventSource connections | `fetch` hangs with no error while the dot stays green | `return () => es.close()`; one stream per app | 6 connections per origin — 3 tabs, or 1 tab with a leak plus a reload |
| Ten `ResponsiveContainer`s in the watchlist | ResizeObserver churn on every render | Fixed `width`/`height` for sparklines | 10 rows, the spec'd default |
| Snapshot task writing every 30 s regardless | `portfolio_snapshots` grows unboundedly; P&L query slows | PLAN.md's "skip when unchanged" rule — implement it, do not defer it | ~1 day of idle uptime |
| `uvicorn --workers > 1` | Prices disagree with fills; duplicate snapshots | Single worker, documented in `main.py` | Any N > 1 |

## Security Mistakes

Auth is out of scope by design (local single-user, no login). These are the ones that still matter.

| Mistake | Risk | Prevention |
|---|---|---|
| Committing `db/finally.db` | Leaks whatever session state was in it into every clone; a real risk once chat transcripts land in it | `git rm --cached`, ignore `db/*.db*` |
| Rendering LLM `message` as HTML | The model's output is untrusted text; prompt injection via a ticker name or a pasted article becomes stored XSS in `chat_messages` | Render as text. React escapes by default — do not reach for `dangerouslySetInnerHTML` for markdown without sanitizing |
| Interpolating the ticker into SQL | The ticker reaches the DB from the LLM as well as the user | Parameterized queries everywhere; `normalize_ticker()` + `^[A-Z]{1,5}$` is a format check, not a SQL defence |
| API keys in error messages | `OPENROUTER_API_KEY` / `MASSIVE_API_KEY` leaking into a chat error surfaced to the UI | Catch provider exceptions at the router boundary and return a generic message; CONCERNS.md already flags keeping keys out of logs |
| `--env-file .env` with the file tracked | `.env` is correctly ignored today (`.gitignore:138`) — keep it that way when `.env.example` is added | Commit `.env.example` with empty values only |
| Trusting `^[A-Z]{1,5}$` as validation of a real company | The simulator synthesizes params for anything, so a hallucinated symbol is indistinguishable from a real one | Accept it (it is the design), but do not describe it as validation |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---|---|---|
| Empty heatmap on first launch | The single most visually distinctive panel is a blank rectangle at the moment of first impression | Explicit empty state with a call to action; PLAN.md already does this for sparklines via history backfill — do the same here |
| Connection dot flashes yellow on every tab switch | Looks broken during a demo where the presenter switches windows | Reset the silence timer on `visibilitychange`; background tabs are throttled by design |
| `-0.00` in red in the positions table | Reads as a loss on a position that has not moved | Treat `|x| < 0.005` as flat for both formatting and colour |
| Fill price differs from the clicked price with no explanation | Feels like a bug even though PLAN.md specifies it | Show the fill explicitly in the confirmation ("Filled 10 AAPL @ $190.52"), which the spec's response shape already supports |
| A trade error surfaced as a raw 500 | The user clicks Buy and nothing happens | PLAN.md's messages are written to be shown verbatim — surface `detail` in the trade bar, and never let a `SQLITE_BUSY` reach the user as a 500 |
| A dust position that cannot be sold or removed | A dead row the user cannot clear, forever | The epsilon deletion rule (pitfall 4) |
| The AI trades on a question | Loss of trust in the copilot in one turn | Prompt rule + notional cap (pitfall 6b) |
| Loading indicator absent during LLM calls | The panel looks frozen for 1–3 s | PLAN.md requires it — verify it is wired to request state, not to a timer |

## "Looks Done But Isn't" Checklist

- [ ] **API routing:** works in tests, shadowed in the container — verify `curl -sI localhost:8000/api/health` returns `content-type: application/json` against the **built image**
- [ ] **Sell all:** verify with fractional quantities (`0.1 × 3`, then sell `0.3`), not just `10` then `10`; assert the position row is **deleted** and the ticker can then be removed from the watchlist
- [ ] **Insufficient cash:** verify "buy the maximum the UI displays" succeeds; the two numbers in the error must never be equal
- [ ] **SSE cleanup:** count `SSE client connected` lines in the backend log — exactly one per page load in a production build
- [ ] **Chat:** verify the container has `litellm` (`docker run --rm finally python -c "import litellm"`), not just the local venv
- [ ] **Structured output:** verify against the **live** LLM, not only `LLM_MOCK=true`; mock mode proves the execution path, not the parsing path
- [ ] **LLM trades:** verify a question ("should I sell TSLA?") returns `trades: []`
- [ ] **Double submit:** verify pressing Enter twice quickly produces one trade, not two
- [ ] **Heatmap:** verify with 0 positions, 1 position, and a losing position — three separate states
- [ ] **Charts:** verify in Firefox, not only Chrome (`ResponsiveContainer` flex behavior diverges)
- [ ] **Static assets:** verify `/_next/static/...` returns 200, not just that `/` returns 200
- [ ] **Scripts:** verify `start_mac.sh` has LF line endings after a fresh `git clone` on a Windows machine
- [ ] **E2E:** run the full suite **twice in a row** without resetting anything; if the second run fails, the tests are asserting on absolute state
- [ ] **Health:** verify `newest_price_age_seconds` actually moves — a frozen market task with a live SSE connection is the hardest failure to see
- [ ] **Restart:** stop the container and start it again; verify cash, positions, watchlist and chat history all survive, and that `open_price` resetting is understood as intended

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---|---|---|
| Static mount shadowing the API | LOW | Move `app.mount` below the routers; one line |
| `db/finally.db` tracked | LOW | `git rm --cached`, update `.gitignore`; history rewrite unnecessary at 94 KB |
| CRLF in shell scripts | LOW | Add `.gitattributes`, `git add --renormalize .` |
| Missing `litellm` in the lock | LOW | `uv add litellm`, commit `uv.lock`, rebuild |
| Recharts re-render storm | MEDIUM | Add `memo`/`useMemo`/animation flags; if state architecture is wrong, restructure the provider tree |
| `ResponsiveContainer` collapse | LOW | Explicit heights plus `min-h-0` on ancestors |
| Float dust positions | MEDIUM | Add epsilon rules, then one-off `DELETE FROM positions WHERE quantity < 1e-9`; retrofit touches every trade path |
| SQLite `BUSY` under load | MEDIUM | Add WAL + `busy_timeout` + `BEGIN IMMEDIATE`; if connections are shared across threads, refactor to per-request |
| SQLite on a OneDrive bind mount | MEDIUM | Relocate the mount source; if the DB is already corrupt, delete it and let lazy init reseed — losing the portfolio |
| LLM double execution | HIGH | The trades already happened. No undo exists (no realized-P&L tracking). Only recovery is deleting the DB and restarting the demo — which is why prevention matters here more than anywhere else |
| Playwright SSE test approach wrong | LOW | Swap `page.route` for `context.setOffline` |
| Project inside OneDrive | MEDIUM | Move the whole tree, re-clone, reinstall `node_modules` and `.venv`. Cheapest before step 4 creates `node_modules`; expensive after |

## Pitfall-to-Phase Mapping

Phases named by PLAN.md section 13 build order.

| Pitfall | Prevention Phase | Verification |
|---|---|---|
| 1. SQLite on OneDrive/Windows bind mount | Phase 0 (environment) | Run 200 trades in a loop against the container; zero `database is locked` |
| 2. `db/finally.db` tracked | Phase 0 (housekeeping) | `git ls-files db/` returns only `.gitkeep` |
| 11. CRLF line endings | Phase 0 (housekeeping) | `file scripts/*.sh` reports "ASCII text" not "with CRLF line terminators" |
| 17. `litellm` lock drift | Phase 0, enforced step 7 | `uv lock --check` exits 0; `docker run --rm finally python -c "import litellm"` |
| 21. OneDrive + node_modules + long paths | Phase 0, before step 4 | `npm ci` completes without `EPERM`/`EBUSY` |
| 4. Float money math | Step 2 (DB + portfolio) | Unit tests: `0.1×3` then sell `0.3` deletes the row; buy-max-displayed-cash succeeds |
| 5. SQLite BUSY / `BEGIN IMMEDIATE` | Step 2 | Concurrent test: snapshot task at 100 ms plus a trade loop, zero errors |
| 3. Static mount + trailing slash + missing dir | Step 2 (app assembly), re-verified step 7 | `curl -sI /api/health` → `application/json` **against the image** |
| 15. Compression middleware vs SSE | Step 2 | SSE frames arrive at ~2 Hz, not in clumps |
| 10. `--workers > 1` | Step 7, constraint noted in step 2 | `fill_price` matches the streamed price within one tick |
| 16. Watchlist/market-source drift | Step 3 (watchlist) | `/api/health` `tickers_cached` equals the watchlist count after add/remove/restart |
| 8. StrictMode EventSource leak | Step 4 (frontend shell) | Exactly one `SSE client connected` per production page load |
| 12. Recharts re-render storm | Step 5 (charts), architecture decided step 4 | DevTools profile: no `recharts` frames dominating; stable memory over 20 min |
| 13. `ResponsiveContainer` collapse | Step 5 | All four chart panels render in Chrome **and** Firefox |
| 14. Treemap zero/negative clamp | Step 5 | Renders correctly with 0, 1, and mixed-sign positions |
| 7. Structured output failures | Step 6 (LLM) — spike first | 20 live chat turns produce 20 parseable responses; no fences or Harmony tokens in the UI |
| 6. LLM auto-execution hazards | Step 6 | A question returns `trades: []`; double-Enter produces one trade; a >50%-notional LLM trade is refused |
| 18. Next export path | Step 7 (Docker) | `/_next/static/*` returns 200; build-time `test -d` assertion |
| 22. PowerShell script quirks | Step 7 | Both start scripts run twice in a row without error |
| 19. E2E state persistence | Step 8 (E2E) | Full suite passes twice consecutively |
| 20. Live-UI assertions | Step 8, hooks added steps 4–5 | No `waitForTimeout` in the suite; no assertion on an absolute price |
| 9. Playwright SSE interception | Step 8 | The resilience test **fails** when the stream is deliberately broken |

## Sources

Confidence tiers obtained from `gsd-tools query classify-confidence`. Web-search-derived findings are MEDIUM; findings read directly from primary source code or verified against this repository's git state are marked HIGH inline.

**Primary source code, read directly (HIGH):**
- `encode/starlette` — `starlette/staticfiles.py` (`get_response`, `lookup_path`, `404.html` fallback, directory redirect)
- `recharts/recharts` — `src/chart/Treemap.tsx` (`computeNode`, `getAreaOfChildren` value clamping; squarify guard)
- This repository: `backend/app/market/stream.py`, `backend/pyproject.toml`, `.gitignore`, `git ls-files db/`, `git config core.autocrlf`

**Official documentation and issue trackers (MEDIUM):**
- OpenRouter — Structured Outputs guide; provider routing `require_parameters`
- Next.js — Static Exports guide (`output: 'export'`, `trailingSlash`)
- MDN — `EventSource`, Using server-sent events
- Playwright — Network / Route API; `microsoft/playwright#15353` (EventSource interception)
- Astral uv — Locking and syncing; Using uv in Docker
- Docker — Bind mounts (networked filesystem warning); `docker/for-win#11`; Docker forums thread 13757 (SQLite locked on Windows volumes)
- `recharts#945` (animation still fires with `isAnimationActive={false}`), `recharts#2251` (ResponsiveContainer in grid/flex), `recharts#1295` (empty data)
- `lmstudio-ai/lmstudio-bug-tracker#1105`, Groq community "Structured Outputs ignored by openai/gpt-oss-120b"
- `NVIDIA/TensorRT-LLM#9256`, `sgl-project/sglang#10061`, `vllm-project/vllm#37030`, `openai/harmony#80` (Harmony channel/token leakage)
- SQLite locking documentation; "SQLite concurrent writes and database is locked errors" (tenthousandmeters); WAL/busy_timeout benchmarks
- Microsoft Q&A — OneDrive subfolder exclusion (unavailable); Files On-Demand access-denied for non-Explorer readers; `pnpm#7592`

**Project documents:**
- `planning/PLAN.md` (authoritative product spec, sections 2–14)
- `.planning/PROJECT.md`, `.planning/codebase/CONCERNS.md`

---
*Pitfalls research for: single-container FastAPI + SSE + static-Next.js + SQLite + LLM-tool-execution trading workstation*
*Researched: 2026-08-05*
