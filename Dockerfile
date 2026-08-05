# FundFlow AI — backend image (Railway entry point)
# This Dockerfile lives at the REPO ROOT and uses the `backend/`
# directory as its source. It is the monorepo-aware variant of
# `backend/Dockerfile` (the single-service variant for Render).
#
# Railway's build context is always the repo root. The Dockerfile
# below references `backend/` explicitly so the build works without
# changing the application code in any way.

FROM python:3.11-slim

# Avoid bytecode (.pyc) and force unbuffered stdout so logs are
# visible in docker logs / Railway / Render.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first — this layer is cached as long as
# requirements.txt doesn't change.
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend source (main.py, app/, etc.).
COPY backend/ .

# Default data location inside the container. Override at runtime with
# `-e FUNDFLOW_DATA_DIR=/data` and `-v fundflow-data:/data`.
ENV FUNDFLOW_DATA_DIR=/data

# Uvicorn listens on this port. Railway injects $PORT automatically —
# fall back to 8000 for local Docker.
ENV PORT=8000

EXPOSE 8000

# `ENVIRONMENT=production` disables the file-watcher reload and silences
# DEBUG-level SQL echo.
ENV ENVIRONMENT=production

# Health check — Railway / Docker Compose / Render use this. The
# endpoint returns 200 with `{"status":"healthy"}`.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:'+__import__('os').environ.get('PORT','8000')+'/api/health', timeout=3).read()" || exit 1

# Single worker for SQLite safety. Increase only after migrating to
# PostgreSQL or after enabling WAL mode + connection pooling.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
