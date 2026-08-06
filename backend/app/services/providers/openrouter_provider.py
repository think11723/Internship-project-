"""OpenRouter provider — secondary fallback in the AIGateway chain.

OpenRouter exposes an OpenAI-compatible API at
``https://openrouter.ai/api/v1``. We use the same ``openai`` SDK
the original code used; only the ``base_url`` and model name change.
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


class OpenRouterProvider(Provider):
    name = "openrouter"
    base_url = "https://openrouter.ai/api/v1"
    api_key_attr = "OPENROUTER_API_KEY"

    def __init__(self) -> None:
        super().__init__(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=self.base_url,
            default_model=settings.OPENROUTER_MODEL
            or "anthropic/claude-3.5-sonnet",
        )

    def _call_provider(self, messages, model, **kwargs):
        if not self.api_key:
            raise AuthError("OPENROUTER_API_KEY not configured")
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
            raise RateLimitError(f"OpenRouter 429: {e}") from e
        except APITimeoutError as e:
            raise TimeoutError_(f"OpenRouter timeout: {e}") from e
        except AuthenticationError as e:
            raise AuthError(f"OpenRouter auth failed: {e}") from e
        except NotFoundError as e:
            raise ModelUnavailableError(f"OpenRouter model not found: {e}") from e
        except APIConnectionError as e:
            raise NetworkError(f"OpenRouter network error: {e}") from e
        except Exception as e:
            status = getattr(e, "status_code", None) or getattr(e, "status", None)
            if status and 500 <= int(status) < 600:
                raise ServerError(f"OpenRouter {status}: {e}") from e
            raise ProviderError(f"OpenRouter error: {e}") from e

        content = ""
        for choice in getattr(response, "choices", []) or []:
            message = getattr(choice, "message", None)
            if message is not None and getattr(message, "content", None):
                content = message.content
                break
        if not content:
            raise ProviderError("OpenRouter returned empty content")
        return content.strip()
