#!/usr/bin/env bash
# Run YuktiCode locally without docker compose.
# Requires: PostgreSQL, RabbitMQ, Redis, MinIO, and Docker (for code judging).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
PID_DIR="$ROOT/.local/pids"
LOG_DIR="$ROOT/.local/logs"

mkdir -p "$PID_DIR" "$LOG_DIR" "$ROOT/.local/minio-data"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

check_port() {
  ss -tln 2>/dev/null | rg -q ":$1\\s" || netstat -tln 2>/dev/null | rg -q ":$1\\s"
}

echo "==> Checking prerequisites..."
require_cmd python3
require_cmd npm
require_cmd node

for svc in "PostgreSQL:5432" "RabbitMQ:5672" "Redis:6379" "MinIO:9005"; do
  name="${svc%%:*}"
  port="${svc##*:}"
  if check_port "$port"; then
    echo "  OK  $name (port $port)"
  else
    echo "  !!  $name is not listening on port $port"
    if [ "$name" = "MinIO" ]; then
      echo "      Start MinIO, e.g.:"
      echo "        MINIO_ROOT_USER=minioadmin MINIO_ROOT_PASSWORD=minioadmin \\"
      echo "          minio server $ROOT/.local/minio-data --address :9005 --console-address :9001"
    fi
    exit 1
  fi
done

if ! docker info >/dev/null 2>&1; then
  echo "  !!  Docker daemon is not running."
  echo "      The API/frontend will start, but code submission/run will return SYSTEM_ERROR."
  echo "      Start Docker Desktop or the system Docker service for judging to work."
fi

echo "==> Installing backend deps (if needed)..."
cd "$BACKEND"
python3 -m pip install -q -r requirements.txt python-jose[cryptography] python-multipart minio python-dotenv

echo "==> Checking database connection..."
if ! python3 - <<'PY'
import asyncio
import sys
from server.config import DATABASE_URL
import asyncpg
import re

m = re.match(r"postgresql\+asyncpg://([^:]+):([^@]+)@([^:/]+):(\d+)/(.+)", DATABASE_URL)
if not m:
    print(f"Invalid DATABASE_URL format: {DATABASE_URL}", file=sys.stderr)
    sys.exit(1)

user, password, host, port, database = m.groups()

async def main():
    try:
        conn = await asyncpg.connect(
            user=user, password=password, host=host, port=int(port), database=database
        )
        await conn.close()
    except Exception as exc:
        print(f"Database connection failed: {exc}", file=sys.stderr)
        print("Update DATABASE_URL in backend/.env with your local PostgreSQL credentials.", file=sys.stderr)
        sys.exit(1)

asyncio.run(main())
PY
then
  exit 1
fi

echo "==> Running migrations..."
python3 -m alembic upgrade head

echo "==> Seeding database (safe to re-run)..."
python3 seed.py

start_bg() {
  local name="$1"
  shift
  local log="$LOG_DIR/$name.log"
  echo "==> Starting $name (log: $log)"
  nohup "$@" >"$log" 2>&1 &
  echo $! >"$PID_DIR/$name.pid"
}

stop_all() {
  for f in "$PID_DIR"/*.pid; do
    [ -f "$f" ] || continue
    kill "$(cat "$f")" 2>/dev/null || true
    rm -f "$f"
  done
}

trap stop_all EXIT

start_bg backend uvicorn server.main:app --host 127.0.0.1 --port 9000 --reload --app-dir "$BACKEND"
start_bg submit-worker python3 "$BACKEND/worker/submit_worker.py"
start_bg run-worker python3 "$BACKEND/worker/run_worker.py"

cd "$FRONTEND"
if [ ! -d node_modules ]; then
  echo "==> Installing frontend deps..."
  npm install
fi

echo
echo "============================================"
echo " YuktiCode is starting locally"
echo " Frontend:  http://localhost:5173"
echo " API docs:  http://127.0.0.1:9000/docs"
echo " Logs:      $LOG_DIR"
echo " Stop:      Ctrl+C"
echo "============================================"
echo

npm run dev
