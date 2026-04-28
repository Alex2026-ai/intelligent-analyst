# Multi-stage build for ia-api
# Base image pinned — never use 'latest' (versioning.md)
# Build context: repo root (docker build -f apps/api/Dockerfile .)

# === Builder stage ===
FROM python:3.11.8-slim AS builder

WORKDIR /build

# Install production dependencies
COPY apps/api/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Install shared package
COPY packages/shared /tmp/shared
RUN pip install --no-cache-dir --prefix=/install /tmp/shared

# Copy application source — preserve full path for import compatibility
# Include __init__.py at each level so Python recognizes the package hierarchy
COPY apps/__init__.py apps/__init__.py
COPY apps/api/__init__.py apps/api/__init__.py
COPY apps/api/src/ apps/api/src/

# === Runtime stage ===
FROM python:3.11.8-slim AS runtime

# Non-root user
RUN groupadd -r iaapi && useradd -r -g iaapi -d /app -s /sbin/nologin iaapi

WORKDIR /app

# Copy installed packages (includes ia-shared)
COPY --from=builder /install /usr/local

# Copy application code — preserve apps/api/src/ path so imports work
COPY --chown=iaapi:iaapi --from=builder /build/apps/__init__.py ./apps/__init__.py
COPY --chown=iaapi:iaapi --from=builder /build/apps/api/__init__.py ./apps/api/__init__.py
COPY --chown=iaapi:iaapi --from=builder /build/apps/api/src/ ./apps/api/src/

# No secrets in image layers
# Secrets come from Secret Manager at runtime

USER iaapi

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live')" || exit 1

ENTRYPOINT ["python", "-m", "uvicorn", "apps.api.src.main:create_app", "--host", "0.0.0.0", "--port", "8000", "--factory"]
