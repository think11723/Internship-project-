"""
FundFlow AI - Main Application Entry Point

This is the entry point for the FastAPI backend application.
"""

import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings, validate_settings
from app.core.logging import setup_logging
from app.core.exceptions import setup_exception_handlers
from app.core.middleware import ValidationMiddleware
from app.db.session import engine, Base
from app.api.routes import health, resume, companies, documents, workflow

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


def _prewarm_discovery_cache() -> None:
    """Pre-warm the discovery cache in a background thread.

    Runs ``_load_companies`` once so the first user request to
    ``/api/companies`` or the orchestrator hits a warm cache instead
    of paying the discovery latency on the hot path. Failures are
    non-fatal — the cache fallback (now caching the seed on failure)
    ensures the next request is still fast.
    """
    try:
        from app.services.orchestrator import _load_companies
        companies = _load_companies()
        logger.info("Pre-warmed discovery cache with %d companies", len(companies))
    except Exception as exc:
        logger.warning("Pre-warm discovery cache failed: %s", exc)


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
