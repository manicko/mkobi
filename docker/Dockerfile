# =============================================================================
# Optimized Multi-stage Dockerfile for mkobi
# FASTER builds: stable base, minimal layers, optimized caching
# Targets: dev (hot reload), test, prod (default)
# =============================================================================

# -----------------------------------------------------------------------------
# Stage: frontend-builder - Build React SPA inside Docker
# -----------------------------------------------------------------------------
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# Copy package files first for layer caching
COPY frontend/package*.json ./

# Install dependencies (no cache mount - must persist to image layer for npm run build)
RUN npm ci

# Copy frontend source and build
COPY frontend/ ./
RUN npm run build

# -----------------------------------------------------------------------------
# Stage: base - Stable Python 3.12 on Debian Bookworm (FAST mirrors)
# Includes build tools for dev/test stages
# -----------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS base

# Configure Debian mirror (configurable via --build-arg)
ARG DEBIAN_MIRROR=deb.debian.org

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Configure Debian mirror
RUN rm -f /etc/apt/sources.list.d/*.sources && \
    echo "deb http://${DEBIAN_MIRROR}/debian bookworm main" > /etc/apt/sources.list && \
    echo "deb http://${DEBIAN_MIRROR}/debian-security bookworm-security main" >> /etc/apt/sources.list && \
    echo "deb http://${DEBIAN_MIRROR}/debian bookworm-updates main" >> /etc/apt/sources.list

# Install system deps (build-essential and libpq-dev for compilation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv via official installer (pinned version for reproducibility)
ARG UV_VERSION=0.11.16
RUN curl -LsSf https://astral.sh/uv/${UV_VERSION}/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

# Create non-root user
RUN addgroup --system app && adduser --system --group app

# -----------------------------------------------------------------------------
# Stage: prod-base - Minimal runtime base for production
# Contains only runtime dependencies (no build tools)
# -----------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS prod-base

ARG DEBIAN_MIRROR=deb.debian.org

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Configure Debian mirror
RUN rm -f /etc/apt/sources.list.d/*.sources && \
    echo "deb http://${DEBIAN_MIRROR}/debian bookworm main" > /etc/apt/sources.list && \
    echo "deb http://${DEBIAN_MIRROR}/debian-security bookworm-security main" >> /etc/apt/sources.list && \
    echo "deb http://${DEBIAN_MIRROR}/debian bookworm-updates main" >> /etc/apt/sources.list

# Install only runtime dependencies (libpq5 for PostgreSQL, curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv via official installer (pinned version for reproducibility)
ARG UV_VERSION=0.11.16
RUN curl -LsSf https://astral.sh/uv/${UV_VERSION}/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

# Create non-root user
RUN addgroup --system app && adduser --system --group app

# Create data directories with proper permissions for non-root user
RUN mkdir -p /app/data/uploads /app/data/logs /app/data/tmp_uploads && \
    chown -R app:app /app/data

# -----------------------------------------------------------------------------
# Stage: dev - Development image
# Hot reload controlled via docker-compose.override.yml
# -----------------------------------------------------------------------------
FROM base AS dev

# Copy dependency files FIRST for layer caching
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
RUN uv sync --frozen

# Add venv to PATH so uvicorn/uvicorn are found
ENV PATH="/app/.venv/bin:${PATH}"

# Copy remaining files
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Create data directories with proper permissions
RUN mkdir -p /app/data/uploads /app/data/logs /app/data/tmp_uploads && \
    chown -R app:app /app/data && \
    chown -R app:app /app/src

# Run as app user in dev mode
USER app

EXPOSE 8000

# Default CMD - override via docker-compose.override.yml for reload control
CMD ["uvicorn", "src.mkobi.main:app", "--host", "0.0.0.0", "--port", "8000"]

# -----------------------------------------------------------------------------
# Stage: test - Testing environment
# -----------------------------------------------------------------------------
FROM base AS test

COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
RUN uv sync --frozen
ENV PATH="/app/.venv/bin:${PATH}"

COPY tests/ ./tests/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Compose files are asserted by tests/test_config.py (worker command and
# healthcheck wiring), so the test image carries them for inspection.
COPY docker/docker-compose.yml docker/docker-compose.override.yml ./docker/

RUN mkdir -p /app/data/uploads /app/data/logs /app/data/tmp_uploads && \
    chown -R app:app /app/data

USER app

ENV ENV=test \
    DATABASE__DBNAME=bidb_test

CMD ["pytest", "tests/", "-v"]

# -----------------------------------------------------------------------------
# Stage: prod - Production (DEFAULT target - faster rebuilds)
# -----------------------------------------------------------------------------
FROM prod-base AS prod

COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

# Install only production dependencies
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:${PATH}"

# Copy frontend build artifacts from frontend-builder stage
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Copy remaining files
COPY alembic/ ./alembic/
COPY alembic.ini ./

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.mkobi.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
