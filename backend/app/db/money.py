"""Money and quantity rounding — one rule, shared by every trade path.

Phase 3's manual trade endpoint and Phase 6's LLM-driven trade path both route
through these three functions. That shared routing is the point of the service
seam: a second rounding rule in either path would let the same trade produce two
different stored quantities depending on who asked for it.

Rounding applies at the write boundary only. Derived figures - market_value,
unrealized_pnl, total_value - are returned at full float precision and formatted
by the client, because the frontend recomputes them from the SSE price stream on
every frame. A server-side rounding of a derived value would not be
authoritative and would visibly disagree with the client's own arithmetic. This
module therefore exposes no helper that rounds a derived value; adding one would
invite exactly that divergence.

avg_cost stores 4 decimal places rather than 2 because it is a derived ratio
rather than a price the user pays. Rounding it to cents accumulates visible
drift in unrealized P&L across repeated partial buys, so do not "tidy" it to
MONEY_PLACES.

No Decimal and no integer-cents layer: the columns are REAL, and at $10,000
scale float64 has roughly eleven significant digits of headroom past the cent.
The epsilon comparison in is_zero closes the only real gap.
"""

from __future__ import annotations

MONEY_PLACES = 2
QUANTITY_PLACES = 4
QUANTITY_EPSILON = 1e-6


def round_money(value: float) -> float:
    """Round a cash amount to 2 decimal places for storage.

    Uses Python's built-in round(), which resolves an exact binary tie to the
    nearest even last digit rather than rounding half away from zero: round(
    0.125, 2) is 0.12, not 0.13. Most decimal values that look like ties are not
    ties in binary at all, so their binary representation decides instead -
    round(1.005, 2) is 1.0. The tests pin both cases so the contract is asserted
    rather than assumed.
    """
    return round(value, MONEY_PLACES)


def round_quantity(value: float) -> float:
    """Round a share quantity to 4 decimal places for storage.

    Four places is fixed by PLAN.md section 8. Tie-breaking follows the same
    built-in round() rule described on round_money, which matters here because
    the boundary sits where fractional-share arithmetic lands.
    """
    return round(value, QUANTITY_PLACES)


def is_zero(value: float) -> bool:
    """Whether a share quantity should be treated as no holding at all.

    The epsilon is 1e-6: two orders of magnitude below the 4dp quantity
    precision, so it can never swallow a real holding, and far above float noise
    at these magnitudes. A remainder under it after selling an entire position is
    arithmetic residue, never shares the user still owns - which is what keeps a
    full sell from leaving a residual fractional-share row behind.
    """
    return abs(value) < QUANTITY_EPSILON
