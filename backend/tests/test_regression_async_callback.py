"""
Regression tests for worker callback architecture after restoring HTTP webhooks.

Workers use async aio_pika handlers and report verdicts via synchronous
http_callback helpers (report_submit_verdict / report_run_verdict).
"""
import sys
import os
import inspect
from unittest.mock import patch, MagicMock, AsyncMock

import pytest


def _import_worker(module_name: str):
    """Import a worker module with a clean module cache."""
    for key in list(sys.modules):
        if key in ('submit_worker', 'run_worker', 'http_callback'):
            del sys.modules[key]

    worker_dir = os.path.join(os.path.dirname(__file__), '..', 'worker')
    backend_dir = os.path.join(os.path.dirname(__file__), '..')
    sys.path.insert(0, worker_dir)
    sys.path.insert(0, backend_dir)
    return __import__(module_name)


class TestWorkerCallbacksAreAsync:
    """aio_pika consumers require async callbacks."""

    def test_submit_callback_is_coroutine(self):
        sw = _import_worker('submit_worker')
        assert inspect.iscoroutinefunction(sw.submit_callback)

    def test_run_callback_is_coroutine(self):
        rw = _import_worker('run_worker')
        assert inspect.iscoroutinefunction(rw.run_callback)


class TestWorkersReportViaHttp:
    """Verdicts go through http_callback."""

    def test_submit_worker_imports_report_submit_verdict(self):
        sw = _import_worker('submit_worker')
        assert callable(sw.report_submit_verdict)

    def test_run_worker_imports_report_run_verdict(self):
        rw = _import_worker('run_worker')
        assert callable(rw.report_run_verdict)
        assert callable(rw.stream_batch_verdicts)


class TestSubmitCallbackReportsHttp:
    @pytest.mark.asyncio
    async def test_reports_verdict_via_http_on_success(self):
        sw = _import_worker('submit_worker')

        message = AsyncMock()
        message.body = __import__('msgpack').packb({
            "submission_id": 7,
            "language": "py",
            "time_limit": 2000,
            "memory_limit": 256,
            "callback_url": "http://backend:9000/webhook/submit/7",
        })
        message.process = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(),
            __aexit__=AsyncMock(return_value=False),
        ))

        with patch.object(sw, 'fetch_submission_data', new=AsyncMock(return_value={
                "language": "py",
                "time_limit": 2000,
                "memory_limit": 256,
                "src_code": "print(1)",
                "test_cases": [{"input": "", "expected_output": "1"}],
            })), \
             patch.object(sw.judger, 'run_judger', return_value={
                "verdict": "AC", "execution_time_ms": 10.0, "peak_memory_mb": 5.0,
            }), \
             patch.object(sw, 'report_submit_verdict') as mock_report:
            await sw.submit_callback(message)

        mock_report.assert_called_once_with(
            submission_id=7,
            status="AC",
            time_ms=10.0,
            mem_mb=5.0,
            callback_url="http://backend:9000/webhook/submit/7",
        )
