"""Groq provider — primary in the AIGateway fallback chain.

Groq exposes an OpenAI-compatible API at
``https://api.groq.com/openai/v1``. We use the same ``openai`` SDK
that the previous OpenRouter path used, only with a different
``base_url``.

Default model: ``llama-3.1-8b-instant`` (very low latency, suitable
for short completions like cover letters).
"""
from __future__ import annotations

import logging

from app.core.config import settings
from app.services.providers.base import (
    AuthError,
    ModelUnavailableError,
    NetworkError,
    Provider,
    ProviderError,
    RateLimitError,
    ServerError,
    TimeoutError_,
)
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    NotFoundError,
    RateLimitError as OpenAIRateLimitError,
)

logger = logging.getLogger("fundflow.providers")


class GroqProvider(Provider):
    name = "groq"
    base_url = "https://api.groq.com/openai/v1"
    default_model = "llama-3.1-8b-instant"
    api_key_attr = "GROQ_API_KEY"

    def __init__(self) -> None:
        super().__init__(
            api_key=settings.GROQ_API_KEY,
            base_url=self.base_url,
            default_model=self.default_model,
        )

    def _call_provider(self, messages, model, **kwargs):
        if not self.api_key:
            raise AuthError("GROQ_API_KEY not configured")
        try:
            client = self._client()
        except ProviderError:
            raise
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                **kwargs,
            )
        except OpenAIRateLimitError as e:
            raise RateLimitError(f"Groq 429: {e}") from e
        except APITimeoutError as e:
            raise TimeoutError_(f"Groq timeout: {e}") from e
        except AuthenticationError as e:
            raise AuthError(f"Groq auth failed: {e}") from e
        except NotFoundError as e:
            # Model may not exist on this provider.
            raise ModelUnavailableError(f"Groq model not found: {e}") from e
        except APIConnectionError as e:
            raise NetworkError(f"Groq network error: {e}") from e
        except Exception as e:
            status = getattr(e, "status_code", None) or getattr(e, "status", None)
            if status and 500 <= int(status) < 600:
                raise ServerError(f"Groq {status}: {e}") from e
            raise ProviderError(f"Groq error: {e}") from e

        content = ""
        for choice in getattr(response, "choices", []) or []:
            message = getattr(choice, "message", None)
            if message is not None and getattr(message, "content", None):
                content = message.content
                break
        if not content:
            raise ProviderError("Groq returned empty content")
        return content.strip()
