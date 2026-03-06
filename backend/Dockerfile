# ---------------------------------------------------------------------------
# YuktiCode Backend (FastAPI) — Dockerfile
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS base

# System dependencies needed by psycopg2-binary + Docker-in-Docker socket
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (cache layer)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir python-jose[cryptography] python-multipart minio

# Copy application source
COPY . .

# ---------------------------------------------------------------------------
# Default configuration (overridden at runtime via env vars)
# ---------------------------------------------------------------------------
ENV DATABASE_URL=postgresql+asyncpg://judge:judge@postgres:5432/judge \
    RABBITMQ_HOST=rabbitmq \
    MINIO_ENDPOINT=minio:9000 \
    MINIO_ACCESS_KEY=minioadmin \
    MINIO_SECRET_KEY=minioadmin \
    MINIO_SECURE=false

EXPOSE 9000

# Run Alembic migrations then start Uvicorn
CMD ["sh", "-c", "python3 -m alembic upgrade head && uvicorn server.main:app --host 0.0.0.0 --port 9000"]
