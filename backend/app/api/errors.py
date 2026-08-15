"""Mapping the service exception taxonomy onto PLAN.md section 8's envelope.

One handler per class, registered once in create_app(), so every route inherits
the translation and a new service raising Conflict is correctly a 409 the day it
is written. The alternative - try/except in each route - silently 500s the first
time an author forgets it.

There is no row for the built-in ValueError. normalize_ticker and wait_for_price
raise plain ValueError, and both are translated into the taxonomy
at the service seam, so an unexpected ValueError - a pydantic validation failure
inside a handler, or any other defect - falls through to Starlette's 500 with a
traceback in the log rather than being reported to the user as a bad request
carrying the exception's own text.

Starlette resolves a handler by walking the exception's MRO and taking the first
registered class, so the three subclasses stay correctly mapped despite all of
them also being ValueErrors.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.services.errors import Conflict, NotFound, TradeError


def register_exception_handlers(app: FastAPI) -> None:
    """Register the three handlers that turn raised services errors into responses."""

    def _detail(exc: Exception, status_code: int) -> JSONResponse:
        """PLAN.md section 8's envelope: the service-authored message, verbatim.

        str(exc) and never repr(exc): the message is shown to the user, so it
        must not carry a class name, a filesystem path or a traceback.
        """
        return JSONResponse({"detail": str(exc)}, status_code=status_code)

    app.add_exception_handler(Conflict, lambda request, exc: _detail(exc, 409))
    app.add_exception_handler(NotFound, lambda request, exc: _detail(exc, 404))
    app.add_exception_handler(TradeError, lambda request, exc: _detail(exc, 400))
