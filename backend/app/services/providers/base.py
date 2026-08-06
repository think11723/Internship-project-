"""Base provider class — common interface for Groq, OpenRouter, Cerebras.

The base class is API-agnostic; subclasses only need to implement
``_call_provider`` which returns the provider's text content or raises
a typed exception. Everything else (rate-limit detection, retry
classification, prompt construction) is shared.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("fundflow.providers")


# ─── Typed exceptions ─────────────────────────────────────────────────────

class ProviderError(Exception):
    """Base class for all provider errors."""


class RateLimitError(ProviderError):
    """HTTP 429 — provider asked us to slow down."""


class TimeoutError_(ProviderError):
    """Request timed out before the provider responded."""


class ServerError(ProviderError):
    """HTTP 5xx — provider had a server-side error."""


class NetworkError(ProviderError):
    """DNS / TCP / TLS error before the request reached the provider."""


class AuthError(ProviderError):
    """HTTP 401/403 — API key is missing, malformed, or revoked."""


class ModelUnavailableError(ProviderError):
    """The requested model is not available on this provider right now."""


# ─── Base provider ────────────────────────────────────────────────────────

class Provider:
    """Abstract base for LLM providers."""

    name: str = "base"
    base_url: str = ""
    default_model: str = ""
    api_key_attr: str = ""

    def __init__(self, api_key: str = "", base_url: str = "", default_model: str = ""):
        if base_url:
            self.base_url = base_url
        if default_model:
            self.default_model = default_model
        self.api_key = api_key or ""
        # Sprint 9.6 fix: renamed the cached client from `_client` to
        # `_openai_client` so it no longer shadows the `_client()`
        # method below. Every provider subclass calls `self._client()`
        # to lazy-init the OpenAI client; the previous code raised
        # `TypeError: 'NoneType' object is not callable` because
        # `__init__` had set `self._client = None`.
        self._openai_client = None  # lazy-init; do not rename back to _client

    # ── Public API ────────────────────────────────────────────────
    def generate(self, prompt: str, model: Optional[str] = None, **kwargs) -> str:
        """One-shot text generation. Returns the assistant's reply.

        Wraps ``chat`` for convenience.
        """
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages, model=model, **kwargs)

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Multi-message chat. Returns the assistant's reply text."""
        return self._call_provider(messages, model or self.default_model, **kwargs)

    def structured_output(
        self,
        prompt: str,
        schema: Dict[str, Any],
        model: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate a JSON object matching the given schema.

        Default implementation appends a JSON-only instruction to the
        prompt and parses the result. Subclasses may override for
        providers with native JSON-mode support.
        """
        from app.services.providers.json_utils import (
            append_json_instruction,
            parse_json_response,
        )
        messages = [
            {"role": "user", "content": append_json_instruction(prompt, schema)},
        ]
        raw = self.chat(messages, model=model, **kwargs)
        return parse_json_response(raw, schema)

    # ── Internals ───────────────────────────────────────────────
    def _client(self):
        """Lazy-init OpenAI-compatible client pointed at this provider.

        Sprint 9.6 fix: the cached client lives in
        ``self._openai_client`` (not ``self._client``) so this method
        is no longer shadowed by the constructor.
        """
        if self._openai_client is None:
            try:
                from openai import OpenAI
                import httpx
                self._openai_client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    http_client=httpx.Client(timeout=180.0),
                )
            except ImportError as e:
                raise ProviderError(
                    f"openai SDK not available: {e}"
                ) from e
        return self._openai_client

    def _call_provider(
        self,
        messages: List[Dict[str, str]],
        model: str,
        **kwargs,
    ) -> str:
        """Subclasses must implement. Returns the assistant's text or
        raises a typed ``ProviderError`` subclass.
        """
        raise NotImplementedError

    # ── Helpers ────────────────────────────────────────────────
    def is_configured(self) -> bool:
        """True if this provider has a usable API key."""
        return bool(self.api_key)
