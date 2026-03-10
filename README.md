# YuktiCode Online Judge

A full-stack competitive programming platform built with **React**, **FastAPI**, and a sandboxed Docker-based judging pipeline.

![React](https://img.shields.io/badge/React-20232a?style=flat-square&logo=react&logoColor=61DAFB)
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat-square&logo=fastapi)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169e1?style=flat-square&logo=postgresql&logoColor=white)
![RabbitMQ](https://img.shields.io/badge/RabbitMQ-FF6600?style=flat-square&logo=rabbitmq&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-DC382D?style=flat-square&logo=redis&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)
![Nginx](https://img.shields.io/badge/Nginx-009639?style=flat-square&logo=nginx&logoColor=white)

---

## Architecture

```
Browser
  │
  ▼
Nginx (port 80)
  ├── /api/*  ──────► FastAPI (port 9000)  ──► PostgreSQL
  ├── /ws/*   ──────► FastAPI WebSocket        ▲
  │                     │                      │
  │                     ▼                   RabbitMQ
  │            [ Redis Pub/Sub ]               │
  │                     ▲                      │
  └── /*      ──────► Vite SPA (React)         │
                                               │
                                    ┌──────────┴──────────┐
                               submit_worker         run_worker
                                    │                     │
                               Docker Socket         Docker Socket
                                    │                     │
                            judger container      judger container
                                    │
                            MinIO (blob storage)
```

### Request lifecycle (Code Submission)
1. Browser POSTs to `/api/submit` → JWT authenticated
2. FastAPI writes a `PENDING` submission to PostgreSQL, enqueues a job on RabbitMQ
3. **`submit_worker`** dequeues the job, runs it inside an ephemeral Docker container (with strict Isolate sandboxing), collects exact real execution time and peak memory (`max-rss`) from `meta.txt`
4. Worker POSTs the verdict + stats to `/api/webhook/submit/{id}`
5. Webhook stores the result in PostgreSQL and broadcasts the JSON onto a centralized **Redis Pub/Sub** network.
6. The exact FastAPI instance holding the user's **WebSocket** receives the Redis broadcast and pushes it in real-time (no polling)

---

## Features

| Area | Details |
|------|---------|
| **Judge** | AC / WA / TLE / MLE / CE / RE — exact resource stats driven by `isolate` sandbox |
| **Real-time** | WebSocket push from Webhook → Redis Backplane → browser (polling fallback for reliability) |
| **Languages** | Python 3, C++ |
| **Admin Panel** | Problem CRUD, test case management, dry-run per test case, contest CRUD |
| **Auth** | JWT-based register/login; `is_admin` flag for admin routes |
| **Storage** | Problem statements + submission code stored in MinIO (S3-compatible) |
| **Security** | Static analysis (forbidden patterns), sandboxed containers, network disabled |

---

## Quick Start (Docker — recommended)

```bash
git clone https://github.com/your-user/cf-clone
cd cf-clone

# 1. Configure environment (edit as needed)
cp .env.example .env

# 2. Build and start all services
docker compose up --build

# frontend  →  http://localhost
# API docs  →  http://localhost/api/docs
# RabbitMQ  →  http://localhost:15672   (guest / guest)
# MinIO     →  http://localhost:9001    (minioadmin / minioadmin)
# Redis     →  Listening on port 6379
```

> **First run**: Alembic migrations run automatically before the API server starts.
> The judger image is built on first job submission (cached afterwards).

### Make yourself an admin

```bash
docker compose exec postgres psql -U judge -d judge \
  -c "UPDATE users SET is_admin = TRUE WHERE username = 'your_username';"
```

Then visit **http://localhost/admin/problems**.

---

## Local Development (without Docker)

### Prerequisites
- Python 3.12+
- Node 20+
- PostgreSQL 15+
- RabbitMQ 3.13+
- Redis 7+
- MinIO (or any S3-compatible bucket)
- Docker daemon (the judger spawns containers)

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
pip install python-jose[cryptography] python-multipart minio

# Set environment variables (or create a .env for your shell)
export DATABASE_URL="postgresql+asyncpg://judge:judge@localhost:5432/judge"
export RABBITMQ_HOST=localhost
export REDIS_URL="redis://localhost:6379/0"
export MINIO_ENDPOINT=localhost:9005
export JWT_SECRET=dev_secret

# Run migrations
python3 -m alembic upgrade head

# Start API server
uvicorn server.main:app --host 127.0.0.1 --port 9000 --reload
```

### 2. Workers (separate terminals)

```bash
cd backend/worker
python3 submit_worker.py
python3 run_worker.py
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

Set `VITE_API_URL` in a `.env` file at the frontend root if your API is not at `http://127.0.0.1:9000`:
```
VITE_API_URL=http://127.0.0.1:9000
```

---

## Docker files

| File | Purpose |
|------|---------|
| `frontend/Dockerfile` | Multi-stage: Node 20 → `npm run build` → Nginx Alpine serves `/dist` |
| `frontend/nginx.conf` | SPA fallback, `/api/*` proxy, `/ws/*` WebSocket upgrade |
| `backend/Dockerfile` | Python 3.12-slim; runs `alembic upgrade head` then `uvicorn` |
| `backend/Dockerfile.worker` | Two build targets: `submit_worker` and `run_worker`; mounts Docker socket |
| `docker-compose.yml` | Orchestrates all 8 services with health-checks and dependency ordering (includes Redis) |
| `.env.example` | Template for required environment variables |

---

## API Reference

All endpoints are prefixed with `/api` when accessed through Nginx (Docker), or by the root path in local dev.

### Auth
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/auth/register` | Register a new user |
| `POST` | `/auth/login` | Login → returns JWT token |

### Problems & Submissions
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/problems` | — | List published problems |
| `GET` | `/problems/{id}` | — | Problem detail + statement |
| `POST` | `/submit` | ✓ | Submit code for judging |
| `GET` | `/submissions` | ✓ | My submission history |
| `GET` | `/submissions/{id}` | ✓ | Submission detail |
| `POST` | `/run` | — | Run code against custom input |

### WebSocket
| Path | Description |
|------|-------------|
| `WS /ws/submissions/{id}` | Subscribe to live verdict push for a submission |

Response format when verdict arrives:
```json
{ "status": "AC", "execution_time_ms": 134.5, "peak_memory_mb": 18.2 }
```

### Admin (requires `is_admin = true`)
| Method | Path | Description |
|--------|------|-------------|
| `GET/POST` | `/admin/problems` | List / create problems |
| `PATCH/DELETE` | `/admin/problems/{id}` | Update / delete |
| `GET/POST` | `/admin/problems/{id}/testcases` | List / add test cases |
| `PUT/DELETE` | `/admin/problems/{id}/testcases/{tc_id}` | Update / delete test case |
| `POST` | `/admin/problems/{id}/testcases/{tc_id}/run` | Dry-run a test case |
| `GET` | `/admin/run-result/{run_id}` | Poll dry-run result |
| `GET/POST` | `/admin/contests` | List / create contests |
| `PATCH/DELETE` | `/admin/contests/{id}` | Update / delete contest |
| `POST/DELETE` | `/admin/contests/{id}/problems/{pid}` | Add / remove problem |

---

## Testing

See [TESTING.md](TESTING.md) for the full test suite documentation.

```bash
cd backend
# Fast targeted tests (no Docker/DB required)
python3 -m pytest tests/test_regression_queue_names.py \
                  tests/test_regression_async_callback.py \
                  tests/test_worker_messaging.py \
                  tests/test_worker_callback.py -v
```

### End-to-End Testing

```bash
cd e2e_tests
# Complete integration test against a live backend/worker environment
python3 e2e_api_test2.py
```

---

## Project Structure

```
cf-clone/
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── Dockerfile.worker
│   ├── requirements.txt
│   ├── server/
│   │   ├── main.py          # FastAPI app, CORS, lifespan
│   │   ├── routes.py        # /submit, /run, /problems, /ws/submissions/{id}
│   │   ├── auth.py          # JWT auth, /auth/*
│   │   ├── admin.py         # Admin CRUD routes
│   │   ├── ws.py            # WebSocket ConnectionManager
│   │   ├── config.py        # Queue names, env vars
│   │   ├── messaging.py     # RabbitMQ async client
│   │   ├── blob_storage.py  # MinIO helpers
│   │   └── db/
│   │       ├── models.py    # SQLAlchemy ORM models
│   │       ├── database.py  # Async session factory
│   │       └── alembic/     # Migration scripts
│   ├── worker/
│   │   ├── submit_worker.py # Async aio_pika worker
│   │   ├── run_worker.py
│   │   └── Judger/
│   │       ├── judger.py       # run_judger, custom_run (returns stats dict)
│   │       ├── docker_manager.py
│   │       ├── file_utils.py
│   │       ├── result_mapper.py
│   │       └── languages/
│   └── tests/               # See TESTING.md
├── e2e_tests/               # End-to-end API tests
│   ├── e2e_api_test2.py
│   ├── e2e_api_test.py
│   └── e2e_test.py
└── frontend/
    ├── Dockerfile
    ├── nginx.conf
    ├── src/
    │   ├── pages/
    │   │   ├── admin/       # AdminLayout, ProblemsPage, ProblemEditPage, ContestsPage
    │   │   └── ...          # HomePage, ProblemsPage, ProblemDetailPage, ...
    │   ├── components/      # Navbar, AdminRoute, Footer, ...
    │   └── context/         # AuthContext
    └── ...
```

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/my-feature`)
3. Commit your changes (`git commit -m 'feat: add my feature'`)
4. Push to the branch (`git push origin feat/my-feature`)
5. Open a Pull Request
