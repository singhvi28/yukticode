# Tests Documentation

This directory contains the automated test suite for the CF-Clone backend. The tests use `pytest` and heavily utilize `unittest.mock` to ensure fast, isolated execution without requiring a live RabbitMQ broker, Docker daemon, or external HTTP targets.

## Running the Tests

To run the entire test suite:
```bash
pytest -v
```

## Structure

- **`test_auth_routes.py`**: Validates the `/auth/register` and `/auth/login` FastAPI endpoints. Uses `pytest-asyncio` and completely mocks the PostgreSQL database using an in-memory `sqlite+aiosqlite:///:memory:` connection scoped to the application's dependency injection to ensure safe integration testing.
- **`test_docker_manager.py`**: Validates the `DockerManager` logic—specifically that ephemeral containers (`auto_remove=True`) are provisioned with proper resource limits, capabilities (`SYS_ADMIN`), and disabled AppArmor profiles for Isolate compatibility.
- **`test_judger_core.py`**: Tests the core orchestration loop in `judger.run_judger` and `judger.custom_run`. Mocks out the Docker layer to test AC, WA, CE, TLE, RE, and MLE judgments. Includes comprehensive validation for Static Analysis blocking forbidden library calls (`os.system`, `popen`) raising `SecurityViolationException`.
- **`test_judger_compare.py`**: Tests the `compare_outputs` judger helper for whitespace-insensitive, judge-friendly output verification.
- **`test_judger_file_utils.py`**: Tests the zero-disk in-memory POSIX tar streaming (`put_archive` / `get_archive`) used for container I/O.
- **`test_judger_result_mapper.py`**: Tests the mapping of container exit codes (e.g. 137, 143) to verdict strings.
- **`test_server_config.py`**: Validates RabbitMQ constants and DLX configurations.
- **`test_server_messaging.py`**: Tests the asynchronous `aio-pika` connection strategy and exchange/queue declarations, including the Dead Letter Exchange (DLX).
- **`test_server_models.py`**: Tests Pydantic input models for endpoints, including the updated `SubmitRequest` schema requiring `problem_id`.
- **`test_server_routes.py`**: Tests FastAPI endpoints (`/submit`, `/run`, `/problems`). It intercepts RabbitMQ via `AsyncMock`, mocks MinIO Blob Storage methods (`upload_text`, `download_text`), and uses an in-memory `sqlite+aiosqlite:///:memory:` dependency injection to simulate the database securely without side-effects.
- **`test_worker_callback.py`**: Tests the asynchronous callback delivery mechanism (`httpx`) inside workers, including exponential back-off retries and manual `basic_ack`/`basic_nack` behavior for DLX routing.
- **`test_worker_messaging.py`**: Tests the synchronous `pika` consumer class used by workers (`auto_ack=False`, `prefetch_count=1`).

## Notes on RabbitMQ Mocks

Importing RabbitMQ client modules (`pika`, `aio_pika`) at test collection time can cause networking side effects. To prevent this, `conftest.py` stubs out `sys.modules['pika']` early on. Individual tests that need to test the worker effectively use `patch.dict('sys.modules')` fixtures (like `sw` in `test_worker_callback.py`) to keep the environment clean.
