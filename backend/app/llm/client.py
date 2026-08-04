"""Chat completion via LiteLLM to OpenRouter with Cerebras as the provider.

Three modes, decided in this order: the deterministic mock, a degraded response
when no API key is configured, then the real call. See PLAN.md sections 5 and 9.
"""

from __future__ import annotations

import logging
import os

from litellm import acompletion

from .mock import mock_response
from .prompt import build_messages
from .schema import ChatResponse

MODEL = "openrouter/openai/gpt-oss-120b"
EXTRA_BODY = {"provider": {"order": ["cerebras"]}}
REASONING_EFFORT = "low"
TIMEOUT_SECONDS = 30

NO_KEY_MESSAGE = (
    "No OPENROUTER_API_KEY is configured, so the AI assistant is switched off. "
    "Set one in the .env file at the project root to enable chat. Every other "
    "part of FinAlly works without it."
)
FAILURE_MESSAGE = (
    "Sorry, I could not reach the AI service just now. Nothing was executed. "
    "Please try again in a moment."
)

logger = logging.getLogger(__name__)


async def generate_response(user_message: str) -> ChatResponse:
    """Produce the assistant's reply to a user message. Never raises."""
    if os.getenv("LLM_MOCK", "").strip().lower() == "true":
        return mock_response(user_message)
    if not os.getenv("OPENROUTER_API_KEY", "").strip():
        return ChatResponse(message=NO_KEY_MESSAGE, trades=[], watchlist_changes=[])
    return await _call_model(user_message)


async def _call_model(user_message: str) -> ChatResponse:
    """Ask the model for a structured response, degrading to an apology on failure.

    This is the one place in the backend where catching everything is right: a
    network blip, a timeout or an unparseable reply must not end the user's
    trading session. No actions are returned, so nothing executes on failure.
    """
    try:
        response = await acompletion(
            model=MODEL,
            messages=build_messages(user_message),
            response_format=ChatResponse,
            reasoning_effort=REASONING_EFFORT,
            extra_body=EXTRA_BODY,
            timeout=TIMEOUT_SECONDS,
        )
        return ChatResponse.model_validate_json(response.choices[0].message.content)
    except Exception:
        logger.exception("Chat completion failed")
        return ChatResponse(message=FAILURE_MESSAGE, trades=[], watchlist_changes=[])
