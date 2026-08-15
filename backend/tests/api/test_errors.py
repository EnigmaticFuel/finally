"""Tests for the exception handler table: what it catches and what it must not.

The taxonomy's three classes still answer 400, 404 and 409. Everything else is a
defect, and a defect must reach the client as a 500 that says nothing about
itself - a raised message echoed into the detail field is shown to the user
verbatim, and a pydantic dump carries model names, field paths and the offending
input value with it.

Most tests here build a bare FastAPI app carrying nothing but the handlers and a
handful of raising routes, so the surface under test is the handler table alone
and no route implementation can mask it. The last test uses the real app fixture,
because the point of deleting the blanket row is that the user-facing rejection
did not move.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.api.errors import register_exception_handlers
from app.services.errors import Conflict, NotFound, TradeError

BARE_MESSAGE = "boom"
TRADE_MESSAGE = "Insufficient cash: need $1.00, have $0.00"


class Counted(BaseModel):
    """A one-field model whose construction from a non-numeric string fails.

    Declared locally rather than imported from app/api/models.py: that module
    belongs to another plan in this wave, and the leak under test is pydantic's,
    not any particular model's.
    """

    count: int


@pytest.fixture
def raising_app() -> FastAPI:
    """An app carrying only the handler table and one route per raise."""
    application = FastAPI()
    register_exception_handlers(application)

    @application.get("/bare")
    def _bare() -> None:
        raise ValueError(BARE_MESSAGE)

    @application.get("/pydantic")
    def _pydantic() -> None:
        Counted(count="not-a-number")

    @application.get("/trade")
    def _trade() -> None:
        raise TradeError(TRADE_MESSAGE)

    @application.get("/conflict")
    def _conflict() -> None:
        raise Conflict("held")

    @application.get("/missing")
    def _missing() -> None:
        raise NotFound("gone")

    return application


class TestUnexpectedValueError:
    """A ValueError the service layer did not raise deliberately is a defect."""

    def test_a_bare_value_error_is_a_500_not_a_400(self, raising_app: FastAPI) -> None:
        """The blanket handler reported server defects as client errors; it is gone."""
        client = TestClient(raising_app, raise_server_exceptions=False)
        response = client.get("/bare")
        assert response.status_code == 500

    def test_a_bare_value_error_does_not_echo_its_message(self, raising_app: FastAPI) -> None:
        """detail is shown to the user verbatim, so a defect's text must not reach it."""
        client = TestClient(raising_app, raise_server_exceptions=False)
        assert BARE_MESSAGE not in client.get("/bare").text

    def test_a_pydantic_failure_is_a_500(self, raising_app: FastAPI) -> None:
        """pydantic_core.ValidationError subclasses ValueError, and is not a user error."""
        client = TestClient(raising_app, raise_server_exceptions=False)
        assert client.get("/pydantic").status_code == 500

    def test_a_pydantic_failure_leaks_neither_the_model_nor_the_docs_url(
        self, raising_app: FastAPI
    ) -> None:
        """The dump names the model, the field, the input value and a docs URL."""
        client = TestClient(raising_app, raise_server_exceptions=False)
        body = client.get("/pydantic").text
        assert "Counted" not in body
        assert "errors.pydantic.dev" not in body
        assert "not-a-number" not in body


class TestTaxonomyStatusCodes:
    """The three deliberate classes keep their codes and their messages."""

    def test_a_trade_error_is_a_400_carrying_its_message(self, raising_app: FastAPI) -> None:
        """TradeError is the taxonomy's only 400, and detail is str(exc) exactly."""
        response = TestClient(raising_app).get("/trade")
        assert response.status_code == 400
        assert response.json()["detail"] == TRADE_MESSAGE

    def test_a_conflict_is_a_409(self, raising_app: FastAPI) -> None:
        """MRO resolution picks Conflict's row despite it also being a ValueError."""
        assert TestClient(raising_app).get("/conflict").status_code == 409

    def test_a_not_found_is_a_404(self, raising_app: FastAPI) -> None:
        """Same MRO rule, the other subclass."""
        assert TestClient(raising_app).get("/missing").status_code == 404


class TestHandlerRegistrations:
    """The registration table itself, asserted rather than inferred from a response."""

    def test_the_built_in_value_error_has_no_handler(self) -> None:
        """The deterministic gate on WR-01: no handler broader than the taxonomy."""
        application = FastAPI()
        register_exception_handlers(application)
        assert ValueError not in application.exception_handlers

    def test_all_three_taxonomy_classes_have_handlers(self) -> None:
        """Deleting the blanket row removed nothing the taxonomy needs."""
        application = FastAPI()
        register_exception_handlers(application)
        registered = application.exception_handlers
        assert [cls in registered for cls in (TradeError, Conflict, NotFound)] == [True] * 3


class TestUserFacingRejectionSurvived:
    """The whole point, proven on the assembled app rather than a synthetic one."""

    def test_an_invalid_symbol_is_still_a_readable_400(self, app: FastAPI) -> None:
        """A bad ticker reaches the user unchanged, now through TradeError at the seam."""
        response = TestClient(app).post("/api/watchlist", json={"ticker": "toolong"})
        assert response.status_code == 400
        assert "Invalid ticker symbol" in response.json()["detail"]
