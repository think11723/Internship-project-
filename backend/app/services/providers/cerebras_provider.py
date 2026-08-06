"""Cerebras provider — tertiary fallback in the AIGateway chain.

Cerebras exposes an OpenAI-compatible API at
``https://api.cerebras.ai/v1``. We use the same ``openai`` SDK; only
the ``base_url`` and model name change.
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


class CerebrasProvider(Provider):
    name = "cerebras"
    base_url = "https://api.cerebras.ai/v1"
    default_model = "llama-3.3-70b"
    api_key_attr = "CEREBRAS_API_KEY"

    def __init__(self) -> None:
        super().__init__(
            api_key=settings.CEREBRAS_API_KEY,
            base_url=self.base_url,
            default_model=self.default_model,
        )

    def _call_provider(self, messages, model, **kwargs):
        if not self.api_key:
            raise AuthError("CEREBRAS_API_KEY not configured")
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
            raise RateLimitError(f"Cerebras 429: {e}") from e
        except APITimeoutError as e:
            raise TimeoutError_(f"Cerebras timeout: {e}") from e
        except AuthenticationError as e:
            raise AuthError(f"Cerebras auth failed: {e}") from e
        except NotFoundError as e:
            raise ModelUnavailableError(f"Cerebras model not found: {e}") from e
        except APIConnectionError as e:
            raise NetworkError(f"Cerebras network error: {e}") from e
        except Exception as e:
            status = getattr(e, "status_code", None) or getattr(e, "status", None)
            if status and 500 <= int(status) < 600:
                raise ServerError(f"Cerebras {status}: {e}") from e
            raise ProviderError(f"Cerebras error: {e}") from e

        content = ""
        for choice in getattr(response, "choices", []) or []:
            message = getattr(choice, "message", None)
            if message is not None and getattr(message, "content", None):
                content = message.content
                break
        if not content:
            raise ProviderError("Cerebras returned empty content")
        return content.strip()
