# Test Suite Documentation

The backend test suite lives in `backend/tests/`. All tests use **pytest** with `unittest.mock` — no live RabbitMQ, Docker, or database required for the unit tests.

## Running the Tests

```bash
cd backend

# Full suite (fast unit + slow async integration)
python3 -m pytest tests/ -v

# Fast regression tests only (< 2 seconds, safe to run in CI pre-commit)
python3 -m pytest \
  tests/test_regression_queue_names.py \
  tests/test_regression_async_callback.py \
  tests/test_worker_messaging.py \
  tests/test_worker_callback.py \
  -v

# Single file
python3 -m pytest tests/test_judger_core.py -v

# Show output for passing tests
python3 -m pytest tests/ -v -s
```

## Test Files

### Judger Unit Tests

| File | What it tests |
|------|---------------|
| `test_judger_core.py` | `run_judger` and `custom_run` orchestration: AC, WA, CE, TLE, RE, SYSTEM_ERROR verdicts. Mocks Docker layer. **Now asserts return type is `dict` with `verdict`, `execution_time_ms`, `peak_memory_mb` keys.** Pulls execution metrics directly from the `isolate` sandboxing `meta.txt` log instead of `container.stats`. |
| `test_judger_compare.py` | `compare_outputs` whitespace-insensitive judge comparison |
| `test_judger_file_utils.py` | In-memory POSIX tar streaming (`put_archive` / `get_archive`) used for container I/O |
| `test_judger_result_mapper.py` | Exit code → verdict mapping (e.g. `137 → MLE`, `143 → TLE`) |
| `test_docker_manager.py` | Docker container provisioned with `mem_limit`, `SYS_ADMIN` cap, disabled AppArmor, `auto_remove=True` |

### Server Unit Tests

| File | What it tests |
|------|---------------|
| `test_server_config.py` | RabbitMQ queue names, exchange constants, DLX configuration |
| `test_server_messaging.py` | Async `aio-pika` connection strategy, exchange/queue declarations, Dead Letter Exchange |
| `test_server_models.py` | Pydantic input models: `SubmitRequest` requires `problem_id`; `RunRequest` shape |
| `test_server_routes.py` | FastAPI routes: `/submit`, `/run`, `/problems` — mocks RabbitMQ with `AsyncMock`, mocks MinIO, uses in-memory SQLite for DB |
| `test_auth_routes.py` | `/auth/register`, `/auth/login` — in-memory SQLite via dependency injection |

### Worker Unit Tests

| File | What it tests |
|------|---------------|
| `test_worker_callback.py` | `submit_callback` ACK/NACK behavior; `send_callback` retry logic with exponential back-off. **Mocks return `dict` for `run_judger` (matches updated API).** |
| `test_worker_messaging.py` | Sync `pika` consumer: `auto_ack=False`, `prefetch_count=1`, queue declare with `passive=True` |

### Regression Tests

| File | What it tests | Why it exists |
|------|---------------|---------------|
| `test_regression_queue_names.py` | Workers import `SUBMIT_QUEUE`/`RUN_QUEUE` from `server.config`, not hardcoded strings | Bug: hardcoded names caused silent routing mismatches |
| `test_regression_async_callback.py` | `send_callback` is a sync function using `httpx.Client`; `asyncio.run()` is never called inside pika callbacks. **Updated: `run_judger` and `custom_run` mocks return dict.** | Bug: `asyncio.run()` inside pika callback raises `RuntimeError: loop already running` |

## Mocking Strategy

### RabbitMQ / pika
Importing `pika` at test collection time causes network connection attempts. `conftest.py` stubs `sys.modules['pika']` early. Individual test modules that exercise workers use `patch.dict('sys.modules', {...})` to control the import environment cleanly.

### Database
Tests that exercise FastAPI routes use `sqlite+aiosqlite:///:memory:` injected via FastAPI's dependency override mechanism — no PostgreSQL required.

### Docker / judger
`test_judger_core.py` mocks `DockerManager`, `put_files_to_container`, `extract_file_from_container`, and `language_instance.run()` / `.compile()` at the call site. No Docker daemon is needed.

### run_judger & custom_run return type
`run_judger` and `custom_run` now return a **dict** (not a string). Any test that mocks `judger.run_judger` or `judger.custom_run` must return:
```python
{"verdict": "AC", "execution_time_ms": 50.0, "peak_memory_mb": 12.0}
```

## Coverage Notes

| Scenario | Covered by |
|----------|-----------|
| AC, WA, CE, TLE, RE, SYSTEM_ERROR | `test_judger_core.py` |
| Security: forbidden pattern detection | `test_judger_core.py` |
| Multi-test-case judging | `test_judger_core.py` |
| Worker ACK on success / NACK on failure | `test_worker_callback.py` |
| Retry with exponential back-off | `test_worker_callback.py` |
| Queue name regression | `test_regression_queue_names.py` |
| No asyncio.run() in pika callback | `test_regression_async_callback.py` |
| Pydantic model validation | `test_server_models.py` |
| JWT register / login | `test_auth_routes.py` |

## Adding a New Test

1. Create `tests/test_<component>.py`
2. Use `@pytest.mark.asyncio` for any `async` test functions
3. If importing worker modules, use the `_fresh_import()` helper (see `test_regression_async_callback.py`) to avoid pika patching issues
4. If mocking `run_judger` or `custom_run`, always return a dict:
   ```python
   mock_judger.run_judger.return_value = {
       "verdict": "AC",
       "execution_time_ms": 50.0,
       "peak_memory_mb": 12.0,
   }
   ```
