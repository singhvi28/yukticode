# Tests

See the full test suite documentation at the repo root:  
**[TESTING.md](../../TESTING.md)**

## Quick start

```bash
cd backend

# Fast tests (no Docker / DB required, < 2 seconds)
python3 -m pytest \
  tests/test_regression_queue_names.py \
  tests/test_regression_async_callback.py \
  tests/test_worker_messaging.py \
  tests/test_worker_callback.py -v

# Full suite
python3 -m pytest tests/ -v
```

## Important: `run_judger` returns a dict

As of the resource-monitoring update, `judger.run_judger()` returns a **dict**, not a string.  
Any mock must use:

```python
mock_judger.run_judger.return_value = {
    "verdict": "AC",
    "execution_time_ms": 50.0,
    "peak_memory_mb": 12.0,
}
```
