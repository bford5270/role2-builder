# Multi-stage build for the FastAPI backend.
#
# Designed to land cleanly on:
#   - AWS App Runner (build from this Dockerfile in the source repo)
#   - AWS ECS Fargate (push to ECR, reference from task def)
#   - Railway (Railway autodetects Dockerfile and uses it)
#   - Local docker run for parity with prod
#
# The frontend is built/deployed separately (Next.js → Amplify or Vercel).
#
# Image size considerations:
# - python:3.11-slim is ~50 MB compressed; full python:3.11 is ~150 MB.
# - boto3 + pandas + sqlalchemy + google-genai add ~200 MB of Python deps.
# - Resulting image: ~400 MB compressed. Reasonable for Fargate / App Runner.

# ---- builder stage: install deps into a virtualenv -----------------------
FROM python:3.11-slim AS builder

# Build deps for psycopg2 / pandas (compiled wheels usually exist for slim,
# but keep the build path resilient if a wheel is missing on the target arch).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .

# Install into an isolated venv we'll copy into the runtime stage.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ---- runtime stage: minimal layer with just the venv + app code ----------
FROM python:3.11-slim AS runtime

# libpq5 is the runtime half of psycopg2's libpq dependency. Tini is a tiny
# init that reaps zombies and forwards signals — critical so SIGTERM from
# App Runner / ECS triggers FastAPI's graceful shutdown instead of being
# absorbed by the python process.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        tini \
    && rm -rf /var/lib/apt/lists/*

# Non-root user. App Runner / Fargate let you run as any UID; running as
# non-root reduces blast radius if the container is compromised.
RUN useradd --create-home --shell /bin/bash --uid 10001 app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Default to JSON logs for log aggregators. Override locally with
    # LOG_FORMAT= (empty) for human-readable console output.
    LOG_FORMAT=json \
    LOG_LEVEL=INFO

WORKDIR /app
COPY --chown=app:app backend/ ./backend/

USER app

# App Runner / Fargate inject PORT; default to 8000 for local docker run.
EXPOSE 8000

# Tini as PID 1, then uvicorn. --host 0.0.0.0 so the container is reachable.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
