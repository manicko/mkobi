# =============================================================================
# Optimized Multi-stage Dockerfile for mkobi
# FASTER builds: stable base, minimal layers, optimized caching
# Targets: dev (hot reload), test, prod (default)
# =============================================================================

# -----------------------------------------------------------------------------
# Stage: frontend-builder - Build React SPA inside Docker
# -----------------------------------------------------------------------------
# Pinned by digest (resolved from the registry on 2026-10-05 with
# ``docker buildx imagetools inspect node:20-alpine --format '{{.Manifest.Digest}}'``).
# A floating tag is not a reproducible build input: the same Dockerfile would
# resolve to a different image tomorrow and a rollback would not reproduce.
# The tag is kept alongside the digest for human readability only; the digest
# is what the build resolves.
FROM node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293 AS frontend-builder

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
# Pinned by digest (resolved from the registry on 2026-10-05 with
# ``docker buildx imagetools inspect python:3.12-slim-bookworm --format '{{.Manifest.Digest}}'``).
# The tag is retained for human readability; the digest is the build input.
FROM python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3 AS base

# Debian mirror policy (RULED: state it, do not invent it).
# Default: ``deb.debian.org``, the upstream Debian archive, which is correct for
# a host with unrestricted network access. This argument exists solely so an
# environment behind a regional mirror (a corporate proxy, an air-gapped
# network, a slow path to the Debian pool) can override it with a deliberate,
# recorded ``--build-arg DEBIAN_MIRROR=<host>``. Overriding it changes where
# package bytes are fetched from, so it is an operator decision that must be
# recorded next to the build invocation, not a value to be guessed here. It is
# never overridden by default and is not wired through compose's env surface.
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

# Install uv via the official installer with an integrity check.
# UV_VERSION pins the *path* of the installer (the version whose script runs),
# not the script's integrity: a substituted response at that URL would still
# execute under a plain ``curl | sh``. The installer is therefore downloaded to
# a file, checked against UV_INSTALLER_SHA256, and only run on a match; a
# mismatch aborts the build. The checksum is pinned alongside the version and
# must be refreshed deliberately whenever UV_VERSION moves.
ARG UV_VERSION=0.11.16
ARG UV_INSTALLER_SHA256=b9f925505899533f36a3acfdf8684c661ff2d5c8735f759fca768367b5996123
RUN curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" -o /tmp/uv-install.sh && \
    echo "${UV_INSTALLER_SHA256}  /tmp/uv-install.sh" | sha256sum -c - && \
    sh /tmp/uv-install.sh && \
    rm -f /tmp/uv-install.sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

# Create non-root user
RUN addgroup --system app && adduser --system --group app

# -----------------------------------------------------------------------------
# Stage: prod-base - Minimal runtime base for production
# Contains only runtime dependencies (no build tools)
# -----------------------------------------------------------------------------
# Pinned by digest (resolved from the registry on 2026-10-05, same command as base).
FROM python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3 AS prod-base

# Debian mirror policy: see the ``base`` stage above. Same default, same
# operator-override contract; kept on both stages because they are independent
# images and a mirror override must apply to each.
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

# Install uv via the official installer with an integrity check. See the base
# stage for why the checksum check exists; the same version and checksum govern
# both stages so dev/test and prod resolve to the same uv.
ARG UV_VERSION=0.11.16
ARG UV_INSTALLER_SHA256=b9f925505899533f36a3acfdf8684c661ff2d5c8735f759fca768367b5996123
RUN curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" -o /tmp/uv-install.sh && \
    echo "${UV_INSTALLER_SHA256}  /tmp/uv-install.sh" | sha256sum -c - && \
    sh /tmp/uv-install.sh && \
    rm -f /tmp/uv-install.sh
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
