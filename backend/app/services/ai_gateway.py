"""Sprint 9 — AI Gateway.

Single entry point for every LLM call in the application. Tries each
provider in priority order and falls back on retryable errors.

Priority: Groq → OpenRouter → Cerebras.

A retryable error is anything that suggests "the next provider might
work" — rate limits, timeouts, server errors, network errors. An
authentication error is NOT retryable in the same way (the same key
won't work on a different provider) but we still advance to the next
provider because the keys are different.

If every provider fails, ``AIGateway.generate`` returns ``None`` and
logs the last error. Callers should treat ``None`` as "AI unavailable,
fall back to deterministic output". The application never crashes
because of an LLM failure.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

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
from app.services.providers.groq_provider import GroqProvider
from app.services.providers.openrouter_provider import OpenRouterProvider
from app.services.providers.cerebras_provider import CerebrasProvider

logger = logging.getLogger("fundflow.ai_gateway")


# Default priority order. Groq first because it is fast + free tier.
_DEFAULT_PROVIDER_ORDER = ("groq", "openrouter", "cerebras")


class AIGateway:
    """Provider-fallback LLM gateway.

    The application should never directly instantiate a provider; it
    should call ``AIGateway().generate(...)`` or
    ``AIGateway().chat(...)``. ``AIGateway`` is process-wide cached via
    ``get_gateway()`` so that the provider list is built once and
    shared by every call site.
    """

    def __init__(self, provider_order: Optional[List[str]] = None) -> None:
        all_providers: List[Provider] = [
            GroqProvider(),
            OpenRouterProvider(),
            CerebrasProvider(),
        ]
        self._by_name = {p.name: p for p in all_providers}
        order = list(provider_order or _DEFAULT_PROVIDER_ORDER)
        # Filter to only those in the default list, preserving requested order.
        self._providers: List[Provider] = [
            self._by_name[n] for n in order if n in self._by_name
        ]
        # Append any missing providers (defensive).
        for p in all_providers:
            if p not in self._providers:
                self._providers.append(p)
        self._enabled = {p.name: True for p in self._providers}

    # ── Provider management ────────────────────────────────────────
    def providers(self) -> List[Provider]:
        return list(self._providers)

    def enable(self, name: str) -> None:
        if name in self._enabled:
            self._enabled[name] = True

    def disable(self, name: str) -> None:
        if name in self._enabled:
            self._enabled[name] = False

    def set_enabled(self, name: str, enabled: bool) -> None:
        if name in self._enabled:
            self._enabled[name] = bool(enabled)

    # ── Public API ────────────────────────────────────────────────
    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs,
    ) -> Optional[str]:
        """One-shot text generation with provider fallback.

        Returns the first successful response, or ``None`` if every
        provider failed. Never raises.
        """
        return self.chat([{"role": "user", "content": prompt}], model=model, **kwargs)

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        **kwargs,
    ) -> Optional[str]:
        """Multi-message chat with provider fallback.

        Returns the first successful response, or ``None`` if every
        provider failed. Never raises.
        """
        last_error: Optional[Exception] = None
        for provider in self._providers:
            if not self._enabled.get(provider.name, True):
                continue
            if not provider.is_configured():
                logger.debug(
                    "AIGateway: skipping %s (not configured)",
                    provider.name,
                )
                continue
            try:
                return provider.chat(messages, model=model, **kwargs)
            except AuthError as e:
                # Auth failure is unrecoverable on this provider.
                logger.warning(
                    "AIGateway: %s auth failed (%s); trying next",
                    provider.name, e,
                )
                last_error = e
                continue
            except (RateLimitError, TimeoutError_, ServerError, NetworkError) as e:
                logger.warning(
                    "AIGateway: %s unavailable (%s); trying next",
                    provider.name, e,
                )
                last_error = e
                continue
            except ModelUnavailableError as e:
                logger.warning(
                    "AIGateway: %s model unavailable (%s); trying next",
                    provider.name, e,
                )
                last_error = e
                continue
            except ProviderError as e:
                # Unknown provider error — log and try next.
                logger.warning(
                    "AIGateway: %s error (%s); trying next",
                    provider.name, e,
                )
                last_error = e
                continue
        if last_error is not None:
            logger.error(
                "AIGateway: all providers failed; last error: %s", last_error
            )
        else:
            logger.error(
                "AIGateway: no providers configured (set GROQ_API_KEY, "
                "OPENROUTER_API_KEY, or CEREBRAS_API_KEY)"
            )
        return None

    def structured_output(
        self,
        prompt: str,
        schema: Dict[str, Any],
        model: Optional[str] = None,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """Provider-fallback structured JSON output.

        Returns the parsed JSON dict, or ``None`` if every provider
        failed. Never raises.
        """
        from app.services.providers.json_utils import (
            append_json_instruction,
            parse_json_response,
        )
        messages = [
            {"role": "user", "content": append_json_instruction(prompt, schema)},
        ]
        last_error: Optional[Exception] = None
        for provider in self._providers:
            if not self._enabled.get(provider.name, True):
                continue
            if not provider.is_configured():
                continue
            try:
                raw = provider.chat(messages, model=model, **kwargs)
                if not raw:
                    continue
                return parse_json_response(raw, schema)
            except ProviderError as e:
                logger.warning(
                    "AIGateway.structured_output: %s failed (%s); trying next",
                    provider.name, e,
                )
                last_error = e
                continue
        if last_error is not None:
            logger.error(
                "AIGateway.structured_output: all providers failed; last error: %s",
                last_error,
            )
        return None


# ── Process-wide singleton ─────────────────────────────────────────────

_GATEWAY: Optional[AIGateway] = None


def get_gateway() -> AIGateway:
    """Return the process-wide AI Gateway, constructing it on first call."""
    global _GATEWAY
    if _GATEWAY is None:
        _GATEWAY = AIGateway()
    return _GATEWAY


def reset_gateway() -> None:
    """Drop the cached gateway. Primarily for tests."""
    global _GATEWAY
    _GATEWAY = None
