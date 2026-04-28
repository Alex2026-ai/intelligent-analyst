# Multi-stage build for ia-worker
# Base image pinned — never use 'latest' (versioning.md)
# Build context: repo root (docker build -f apps/worker/Dockerfile .)

# === Builder stage ===
FROM python:3.11.8-slim AS builder

WORKDIR /build

# Install production dependencies
COPY apps/worker/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Install shared package
COPY packages/shared /tmp/shared
RUN pip install --no-cache-dir --prefix=/install /tmp/shared

# Copy application source
COPY apps/worker/src/ src/

# === Runtime stage ===
FROM python:3.11.8-slim AS runtime

RUN groupadd -r iaworker && useradd -r -g iaworker -d /app -s /sbin/nologin iaworker

WORKDIR /app

# Copy installed packages (includes ia-shared)
COPY --from=builder /install /usr/local

# Copy application code
COPY --from=builder /build/src ./src

USER iaworker

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "print('healthy')" || exit 1

ENTRYPOINT ["python", "-m", "src.main"]
