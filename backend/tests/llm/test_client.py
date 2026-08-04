"""generate_response: mode selection, structured parsing, and never raising."""

from types import SimpleNamespace

import pytest

from app.llm import ChatResponse, client, generate_response

VALID_JSON = (
    '{"message": "Buying one share of AAPL.",'
    ' "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 1}],'
    ' "watchlist_changes": []}'
)


def fake_completion(content, calls):
    """An acompletion stub that records its kwargs and returns `content`."""

    async def _acompletion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    return _acompletion


@pytest.fixture
def real_mode(monkeypatch):
    """Neither mocked nor keyless: the real call path, with litellm stubbed out."""
    monkeypatch.setenv("LLM_MOCK", "false")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


async def test_mock_mode_uses_the_mock(market, mock_llm):
    response = await generate_response("buy NVDA")
    assert response.trades[0].ticker == "NVDA"


async def test_mock_mode_is_case_insensitive_on_the_env_var(market, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "TRUE")
    response = await generate_response("how am I doing")
    assert response.message.startswith("You are holding")


async def test_missing_key_degrades_without_raising(market, no_key):
    response = await generate_response("buy NVDA")
    assert "OPENROUTER_API_KEY" in response.message
    assert response.trades == []
    assert response.watchlist_changes == []


async def test_blank_key_is_treated_as_missing(market, monkeypatch):
    monkeypatch.delenv("LLM_MOCK", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "   ")
    response = await generate_response("hello")
    assert "OPENROUTER_API_KEY" in response.message


async def test_real_call_parses_structured_output(market, real_mode, monkeypatch):
    calls = []
    monkeypatch.setattr(client, "acompletion", fake_completion(VALID_JSON, calls))

    response = await generate_response("buy one AAPL")

    assert isinstance(response, ChatResponse)
    assert response.message == "Buying one share of AAPL."
    assert response.trades[0].ticker == "AAPL"
    assert response.watchlist_changes == []


async def test_real_call_routes_to_cerebras_with_the_schema(market, real_mode, monkeypatch):
    calls = []
    monkeypatch.setattr(client, "acompletion", fake_completion(VALID_JSON, calls))

    await generate_response("buy one AAPL")

    assert calls[0]["model"] == client.MODEL
    assert calls[0]["extra_body"] == client.EXTRA_BODY
    assert calls[0]["response_format"] is ChatResponse


async def test_prompt_carries_system_context_and_the_user_message(market, real_mode, monkeypatch):
    calls = []
    monkeypatch.setattr(client, "acompletion", fake_completion(VALID_JSON, calls))

    await generate_response("what should I do")

    messages = calls[0]["messages"]
    assert messages[0]["role"] == "system"
    assert "FinAlly" in messages[0]["content"]
    assert "Cash balance: 10000.00" in messages[1]["content"]
    assert messages[-1] == {"role": "user", "content": "what should I do"}


@pytest.mark.parametrize(
    "content",
    ["not json at all", '{"message": "hi"}', '{"message": "hi", "trades": "nope"}'],
)
async def test_malformed_response_degrades(market, real_mode, monkeypatch, content):
    monkeypatch.setattr(client, "acompletion", fake_completion(content, []))

    response = await generate_response("hello")

    assert response.message == client.FAILURE_MESSAGE
    assert response.trades == []
    assert response.watchlist_changes == []


async def test_network_failure_degrades(market, real_mode, monkeypatch):
    async def boom(**kwargs):
        raise ConnectionError("upstream is down")

    monkeypatch.setattr(client, "acompletion", boom)

    response = await generate_response("hello")

    assert response.message == client.FAILURE_MESSAGE
    assert response.trades == []
