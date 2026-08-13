# Phase 3 Service Seam Contract

Locked by the developer at plan 03-01 Task 1 (option-a). These three functions are
the only doors between the HTTP layer and the business rules. Phase 6 (CHAT-07,
CHAT-08, CHAT-09) is planned against exactly these signatures and calls them
directly, with no FastAPI object in hand.

## The signatures

```python
# app/services/trading.py
async def execute_trade(
    db_path: Path,
    cache: PriceCache,
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
seam, so Phase 6 passes exactly what the router passes. `execute_trade` is D-03
verbatim.

## Why add and remove are asymmetric

`add` takes a `MarketDataSource` because D-09 requires it to register the ticker
with the running feed after the database write. `remove` does not take one because
D-08 removes only the database row: the simulator keeps producing a price for an
unwatched ticker until restart, which is harmless. An unused `source` parameter on
`remove` would be a lie about the dependency, so option-b was rejected.

## Reversibility

One-way. Changing these shapes after Phase 6 lands breaks a cross-phase contract,
not just a call site — it means replanning Phase 6 and rewriting both call sites.
