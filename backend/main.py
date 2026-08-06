"""
FundFlow AI - Main Application Entry Point

This is the entry point for the FastAPI backend application.
"""

import os
import threading
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings, validate_settings
from app.core.logging import setup_logging
from app.core.exceptions import setup_exception_handlers
from app.core.middleware import ValidationMiddleware
from app.db.session import engine, Base
from app.api.routes import health, resume, companies, documents, workflow, career

# Fail fast if required environment variables are missing. This runs
# *before* the FastAPI app is constructed so the failure is loud and
# immediate rather than a confusing 500 on the first request.
validate_settings()

# Setup logging
logger = setup_logging()

# Create FastAPI application
app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add validation middleware
ValidationMiddleware(app)

# Setup exception handlers
setup_exception_handlers(app)

# Include routers
app.include_router(health.router, prefix="/api", tags=["Health"])
app.include_router(resume.router, prefix="/api/resume", tags=["Resume"])
app.include_router(companies.router, prefix="/api/companies", tags=["Companies"])
app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])
app.include_router(workflow.router, prefix="/api/workflow", tags=["Workflow"])
app.include_router(career.router, prefix="/api", tags=["Career"])


def _prewarm_discovery_cache() -> None:
    """Pre-warm the discovery cache in a background thread.

    Uses the deterministic Tavily pipeline (``trigger_weekly_refresh``)
    so the prewarm does not silently degrade to the curated seed when
    the LLM is unavailable. If Tavily itself fails, the cache stays
    empty and the first real request will trigger discovery lazily.
    """
    try:
        from app.services.orchestrator import trigger_weekly_refresh
        result = trigger_weekly_refresh(force=False)
        if result.get("status") == "ok":
            logger.info(
                "Pre-warmed discovery cache: %s companies=%s",
                result.get("status"),
                result.get("companies_count"),
            )
        else:
            logger.info(
                "Pre-warm discovery cache: status=%s",
                result.get("status"),
            )
    except Exception as exc:
        logger.warning("Pre-warm discovery cache failed: %s", exc)


def _scheduler_loop(stop_event: threading.Event, interval_seconds: float) -> None:
    """Run the Weekly Funding Agent every ``interval_seconds`` seconds.

    Uses a ``threading.Event`` for clean shutdown so a future
    FastAPI lifespan migration can ``stop_event.set()`` and the loop
    will exit promptly on its next ``wait`` timeout.
    """
    while not stop_event.is_set():
        # Sleep first — the prewarm already covers the cold start.
        if stop_event.wait(timeout=interval_seconds):
            return
        try:
            from app.services.orchestrator import trigger_weekly_refresh
            result = trigger_weekly_refresh(force=False)
            logger.info(
                "Weekly scheduler tick: status=%s companies=%s",
                result.get("status"),
                result.get("companies_count"),
            )
            # Non-blocking enrichment after discovery. Runs in its
            # own daemon thread so the request path is never blocked.
            if result.get("status") in {"ok", "skipped"}:
                threading.Thread(
                    target=_enrichment_tick,
                    daemon=True,
                    name="company-enrichment-tick",
                ).start()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Weekly scheduler tick failed: %s", exc)


def _enrichment_tick() -> None:
    """Run the Company Intelligence enrichment pass once.

    Pure-deterministic — no LLM dependency. Reads the cache populated
    by the Weekly Funding Agent and adds richer per-company fields
    (careers page URL, LinkedIn, GitHub, founders, investors, tech
    stack, hiring signals, etc.). Existing populated fields are
    never overwritten. Errors per-company are logged but do not
    propagate.
    """
    try:
        from app.services.company_enricher import run_enrichment
        result = run_enrichment(force=False)
        logger.info(
            "Enrichment tick complete: enriched=%s skipped=%s total=%s",
            result.get("enriched"),
            result.get("skipped"),
            result.get("total"),
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Enrichment tick failed: %s", exc)


def _start_weekly_scheduler() -> None:
    """Start the weekly funding scheduler, gated by env flags.

    - ``WEEKLY_AGENT_ENABLED=false`` → no-op (keeps the deployment
      identical to the pre-agent behaviour).
    - ``WEEKLY_AGENT_RUN_ONCE=true`` (intended for CI / one-shot
      local verification) → runs the agent synchronously once on
      startup and does NOT spawn a thread. The next startup or
      POST ``/api/companies/refresh-weekly?force=true`` covers
      subsequent runs.
    - Otherwise → spawn a daemon thread that ticks every
      ``WEEKLY_AGENT_INTERVAL_HOURS``.
    """
    if not settings.WEEKLY_AGENT_ENABLED:
        logger.info("Weekly scheduler disabled (WEEKLY_AGENT_ENABLED=false)")
        return

    interval_seconds = settings.WEEKLY_AGENT_INTERVAL_HOURS * 3600

    if settings.WEEKLY_AGENT_RUN_ONCE:
        logger.info(
            "Weekly agent RUN_ONCE=true — running synchronously on startup"
        )
        try:
            from app.services.orchestrator import trigger_weekly_refresh
            result = trigger_weekly_refresh(force=True)
            logger.info(
                "Weekly agent run-once complete: status=%s companies=%s",
                result.get("status"),
                result.get("companies_count"),
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Weekly agent run-once failed: %s", exc)
        return

    stop_event = threading.Event()
    thread = threading.Thread(
        target=_scheduler_loop,
        args=(stop_event, interval_seconds),
        daemon=True,
        name="weekly-funding-agent-scheduler",
    )
    thread.start()
    logger.info(
        "Weekly scheduler started (interval=%sh, daemon thread)",
        settings.WEEKLY_AGENT_INTERVAL_HOURS,
    )


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup and pre-warm discovery cache."""
    logger.info("Starting FundFlow AI backend...")
    Base.metadata.create_all(bind=engine)
    # Lightweight idempotent migration for columns added after the
    # initial ``create_all`` ran on the existing SQLite database.
    _migrate_existing_schema()
    logger.info("Database initialized successfully")
    # Fire-and-forget background pre-warm; does not block startup.
    threading.Thread(target=_prewarm_discovery_cache, daemon=True).start()
    # Weekly funding scheduler — same pattern; can be disabled via
    # ``WEEKLY_AGENT_ENABLED=false`` (default true).
    _start_weekly_scheduler()


def _migrate_existing_schema() -> None:
    """Add columns that were introduced after the initial DB creation.

    ``Base.metadata.create_all`` only creates missing tables, it does not
    add new columns to existing ones. This is a no-op on every startup
    once the migration has run.
    """
    expected: dict[str, str] = {
        "file_size": "INTEGER",
    }
    try:
        with engine.begin() as conn:
            existing = {
                row[1]
                for row in conn.exec_driver_sql("PRAGMA table_info(resumes)").fetchall()
            }
            for column, type_sql in expected.items():
                if column not in existing:
                    conn.exec_driver_sql(
                        f"ALTER TABLE resumes ADD COLUMN {column} {type_sql}"
                    )
                    logger.info("Migration: added resumes.%s column", column)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Schema migration skipped: %s", exc)


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Shutting down FundFlow AI backend...")


if __name__ == "__main__":
    import os

    import uvicorn

    # ``reload`` enables the file-watcher hot-reload. In production this
    # massively hurts performance and exposes internal endpoints on every
    # file save. Auto-disable outside development.
    is_dev = os.getenv("ENVIRONMENT", "development") == "development"

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=is_dev,
        log_level="debug" if is_dev else "info",
    )
