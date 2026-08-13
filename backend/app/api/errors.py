"""Mapping the service exception taxonomy onto PLAN.md section 8's envelope.

One handler per class, registered once in create_app(), so every route inherits
the translation and a new service raising Conflict is correctly a 409 the day it
is written. The alternative - try/except in each route - silently 500s the first
time an author forgets it.

The bare-ValueError row is load-bearing, not belt-and-braces. normalize_ticker
and wait_for_price both raise plain ValueError, and without that row an invalid
symbol and a price timeout would each surface as a 500 carrying a traceback body
instead of the readable 400 the user is promised.

Starlette resolves a handler by walking the exception's MRO and taking the first
registered class, so the three subclasses stay correctly mapped despite all of
them also being ValueErrors.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.services.errors import Conflict, NotFound, TradeError


def register_exception_handlers(app: FastAPI) -> None:
    """Register the four handlers that turn raised services errors into responses."""

    def _detail(exc: Exception, status_code: int) -> JSONResponse:
        """PLAN.md section 8's envelope: the service-authored message, verbatim.

        str(exc) and never repr(exc): the message is shown to the user, so it
        must not carry a class name, a filesystem path or a traceback.
        """
        return JSONResponse({"detail": str(exc)}, status_code=status_code)

    app.add_exception_handler(Conflict, lambda request, exc: _detail(exc, 409))
    app.add_exception_handler(NotFound, lambda request, exc: _detail(exc, 404))
    app.add_exception_handler(TradeError, lambda request, exc: _detail(exc, 400))
    app.add_exception_handler(ValueError, lambda request, exc: _detail(exc, 400))
