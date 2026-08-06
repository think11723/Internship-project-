"""Application configuration settings.

Defines the ``Settings`` Pydantic model and a startup validation
helper. The validation helper runs before the FastAPI app is built
so a misconfigured deployment fails fast with a clear, actionable
error message instead of returning confusing 500s on the first
request.
"""

import logging
import sys
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings.

    Reads from ``.env`` (case-sensitive). Any unknown env vars are
    ignored (``extra = "ignore"``) so .env typos don't crash boot.
    """

    # Project information
    PROJECT_NAME: str = "FundFlow AI"
    PROJECT_DESCRIPTION: str = "Autonomous Career Intelligence Agent"
    VERSION: str = "0.1.0"

    # API configuration
    API_V1_PREFIX: str = "/api"

    # CORS configuration — populated from .env in production.
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://localhost:3003",
        "http://localhost:3004",
        "http://localhost:3005",
        "http://localhost:3006",
        "http://localhost:3007",
        "http://localhost:3008",
        "http://localhost:3009",
        "http://localhost:3010",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    # Database
    DATABASE_URL: str = "sqlite:///./fundflow.db"

    # Discovery cache TTL in hours
    DISCOVERY_CACHE_HOURS: int = 24

    # ── AI Gateway (Sprint 9) ─────────────────────────────────────────
    # All LLM calls now route through ``app.services.ai_gateway`` with
    # this fallback order: groq → openrouter → cerebras. The gateway
    # only needs ONE provider to succeed; missing keys are skipped
    # silently and the next provider is tried.
    LLM_PROVIDER_ORDER: str = "groq,openrouter,cerebras"
    LLM_PROVIDER_ENABLED: str = ""  # empty = all enabled; comma-separated override

    # Groq (primary — fast + free tier)
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_MODEL: str = "llama-3.1-8b-instant"

    # OpenRouter (fallback)
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL: str = "anthropic/claude-3.5-sonnet"

    # Cerebras (final fallback)
    CEREBRAS_API_KEY: str = ""
    CEREBRAS_BASE_URL: str = "https://api.cerebras.ai/v1"
    CEREBRAS_MODEL: str = "llama-3.3-70b"

    # Environment
    # ``ENVIRONMENT`` switches between ``development`` and ``production``.
    # ``DEBUG`` defaults OFF — flip to True in development .env.
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    # ── Weekly Funding Agent ────────────────────────────────────────────
    # When enabled, a background scheduler in main.py runs the agent
    # every ``WEEKLY_AGENT_INTERVAL_HOURS`` hours, scraping the last
    # ``WEEKLY_AGENT_LOOKBACK_DAYS`` days of funded AI startups into
    # the discovery cache. Set ``WEEKLY_AGENT_RUN_ONCE=true`` in CI
    # (or for one-shot local verification) to trigger a synchronous
    # refresh instead of starting the scheduler thread.
    WEEKLY_AGENT_ENABLED: bool = True
    WEEKLY_AGENT_INTERVAL_HOURS: int = 168  # 7 days
    WEEKLY_AGENT_LOOKBACK_DAYS: int = 7
    WEEKLY_AGENT_RUN_ONCE: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = True
        # Allow additional env vars in .env without raising
        # "Extra inputs are not permitted".
        extra = "ignore"


settings = Settings()


# Required env vars for every deployment. Validation runs *before* the
# FastAPI app is constructed so a misconfigured deployment fails fast
# with a clear, actionable error instead of returning confusing 500s.
# Sprint 9: only DATABASE_URL is hard-required. The AI gateway accepts
# any of the three provider keys; if none are set, the gateway returns
# None on every call (callers fall back to deterministic output).
_REQUIRED_VARS: List[str] = [
    "DATABASE_URL",
]


def validate_settings() -> None:
    """Fail-fast check that every required env var is set.

    Called once from ``main.py`` before the FastAPI app is built. On
    failure, writes a friendly error block to stderr and exits with
    status 1.
    """
    missing = [name for name in _REQUIRED_VARS if not getattr(settings, name, None)]
    if not missing:
        return

    logger = logging.getLogger("fundflow")
    # Stderr so the message survives even if logging isn't fully wired.
    print("", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("FundFlow AI — startup aborted: missing required env vars",
          file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("", file=sys.stderr)
    for name in missing:
        print(f"  - {name}", file=sys.stderr)
    print("", file=sys.stderr)
    print("Copy backend/.env.example to backend/.env and fill in the",
          file=sys.stderr)
    print("values. See README.md > Environment Variables for the full",
          file=sys.stderr)
    print("reference.", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    logger.critical("Missing required env vars: %s", ", ".join(missing))
    raise SystemExit(1)
