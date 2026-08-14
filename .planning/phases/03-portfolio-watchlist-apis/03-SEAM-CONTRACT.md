# Phase 3 Service Seam Contract

Locked by the developer at plan 03-01 Task 1 (option-a). These three functions are
the only doors between the HTTP layer and the business rules. Phase 6 (CHAT-07,
CHAT-08, CHAT-09) is planned against exactly these signatures and calls them
directly, with no FastAPI object in hand.

## Amendment — 2026-08-14 (G-01)

`execute_trade` gains a `source: MarketDataSource` parameter. Decided by the
developer at the phase 03 gap-closing gate, in response to G-01 / CR-02: the
function had no way to register a traded symbol with the running feed, so
"trading an unwatched ticker adds it to the watchlist" (PORT-07, ROADMAP SC2)
was unreachable — `wait_for_price` always expired for a symbol the source had
never been told about.

The amendment makes the seam symmetric: both writers that can introduce a new
symbol now hold the feed they must register it with, which is the same reason
D-09 already gave `watchlist.add` a source. The alternatives were rejected —
a narrow registrar callable adds an indirection with exactly one implementation,
and registering in the callers duplicates the rule at every call site where a
missed one silently reopens G-01.

Amending is cheap now and not later: Phase 6 is planned against this shape but
unbuilt, so the cost is this document plus the phase 03 call sites. The "one-way"
warning below stands for any change made after Phase 6 lands.

**Signature below is the amended one. The pre-amendment shape was**
`execute_trade(db_path, cache, ticker, side, quantity)`.

## The signatures

```python
# app/services/trading.py
async def execute_trade(
    db_path: Path,
    cache: PriceCache,
    source: MarketDataSource,
    ticker: str,
    side: str,
    quantity: float,
) -> TradeResult: ...


# app/services/watchlist.py  (plan 03-04)
async def add(
    db_path: Path,
    source: MarketDataSource,
    ticker: str,
) -> WatchlistEntry: ...


async def remove(
    db_path: Path,
    ticker: str,
) -> None: ...
```

## The rule these follow

`db_path` first, collaborators next, payload last. No FastAPI object crosses the
seam, so Phase 6 passes exactly what the router passes. `execute_trade` was D-03
verbatim until the G-01 amendment above added `source` to its collaborators.

## Why add and remove are asymmetric

`add` takes a `MarketDataSource` because D-09 requires it to register the ticker
with the running feed after the database write. `remove` does not take one because
D-08 removes only the database row: the simulator keeps producing a price for an
unwatched ticker until restart, which is harmless. An unused `source` parameter on
`remove` would be a lie about the dependency, so option-b was rejected.

## Reversibility

One-way. Changing these shapes after Phase 6 lands breaks a cross-phase contract,
not just a call site — it means replanning Phase 6 and rewriting both call sites.
