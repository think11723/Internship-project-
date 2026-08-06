"""Sprint 9 — AI Provider abstraction.

Common interface for all LLM providers. Every provider exposes:

  - generate(prompt, model=None, **kwargs) -> str
  - chat(messages, model=None, **kwargs) -> str
  - structured_output(prompt, schema, model=None, **kwargs) -> dict

Errors raised by the underlying transport are mapped to a small set
of typed exceptions so the AIGateway can decide whether to retry the
next provider.

Provider implementations live in:
  - groq_provider.py
  - openrouter_provider.py
  - cerebras_provider.py
"""
from app.services.providers.base import (
    Provider,
    ProviderError,
    RateLimitError,
    TimeoutError_,
    ServerError,
    NetworkError,
    AuthError,
    ModelUnavailableError,
)

__all__ = [
    "Provider",
    "ProviderError",
    "RateLimitError",
    "TimeoutError_",
    "ServerError",
    "NetworkError",
    "AuthError",
    "ModelUnavailableError",
]
