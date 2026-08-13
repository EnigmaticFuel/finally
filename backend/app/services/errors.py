"""The service exception taxonomy - three classes, three status codes.

Every class subclasses ValueError, so Phase 1's raise-a-ValueError-with-a-
user-facing-message style and wait_for_price's existing plain ValueError both
still fit the same handler table. Nothing under app/services/ imports FastAPI's
HTTP error type: raising is the only signalling mechanism, and app/api/errors.py
owns the translation.

Phase 6's LLM path catches these same classes and reads str(exc) for its
per-action error text, which is why the message on every raise is written to be
shown to the user verbatim.
"""

from __future__ import annotations


class TradeError(ValueError):
    """A trade violated a business rule. Translated to HTTP 400."""


class NotFound(ValueError):  # noqa: N818 - the name is a locked cross-phase contract
    """The named resource does not exist. Translated to HTTP 404."""


class Conflict(ValueError):  # noqa: N818 - the name is a locked cross-phase contract
    """The request contradicts current state. Translated to HTTP 409."""
