import os
from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env for local development (no-op if file is absent)
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# RabbitMQ connection parameters
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")

# Shared secret for HMAC-SHA256 webhook authentication.
# The worker signs the payload; the API server verifies it.
# Set a strong random value in production (e.g. openssl rand -hex 32).
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

# Internal API URL for workers to reach the backend
INTERNAL_API_URL = os.getenv("INTERNAL_API_URL", "http://127.0.0.1:9000")

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

RUN_EXCHANGE = 'run_exchange'
SUBMIT_EXCHANGE = 'submit_exchange'

RUN_ROUTING_KEY = 'run_queue_key'
SUBMIT_ROUTING_KEY = 'submit_queue_key'

RUN_QUEUE = 'run_queue_v2'
SUBMIT_QUEUE = 'submit_queue_v2'

# Dead Letter Exchange (DLX) — receives messages rejected by workers after exhausting retries
DLX_EXCHANGE = 'dlx_exchange'
DLX_RUN_QUEUE = 'dlx_run_queue'
DLX_SUBMIT_QUEUE = 'dlx_submit_queue'

# Database Configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/cfclone",
)
