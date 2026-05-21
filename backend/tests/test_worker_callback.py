"""
Tests for worker/http_callback.py — HTTP verdict reporting helpers.
httpx Client is fully mocked; no network required.
"""
import sys
import os
import json
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'worker'))

import http_callback


def _mock_client():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_resp
    return mock_client


class TestReportSubmitVerdict:
    def test_posts_json_to_webhook(self):
        mock_client = _mock_client()
        with patch.object(http_callback, 'httpx') as mock_httpx, \
             patch.object(http_callback, 'INTERNAL_API_URL', 'http://backend:9000'), \
             patch.object(http_callback, 'WEBHOOK_SECRET', ''):
            mock_httpx.Client.return_value = mock_client
            http_callback.report_submit_verdict(
                submission_id=42, status="AC", time_ms=12.5, mem_mb=8.0,
            )

        mock_client.post.assert_called_once()
        args, kwargs = mock_client.post.call_args
        assert args[0] == "http://backend:9000/webhook/submit/42"
        body = json.loads(kwargs["content"].decode())
        assert body == {
            "status": "AC",
            "execution_time_ms": 12.5,
            "peak_memory_mb": 8.0,
        }


class TestReportRunVerdict:
    def test_posts_json_to_webhook(self):
        mock_client = _mock_client()
        with patch.object(http_callback, 'httpx') as mock_httpx, \
             patch.object(http_callback, 'INTERNAL_API_URL', 'http://backend:9000'), \
             patch.object(http_callback, 'WEBHOOK_SECRET', ''):
            mock_httpx.Client.return_value = mock_client
            http_callback.report_run_verdict(
                run_id="abc", status="AC", std_out="1\n",
                time_ms=3.0, mem_mb=1.5, test_index=0,
            )

        mock_client.post.assert_called_once()
        args, kwargs = mock_client.post.call_args
        assert args[0] == "http://backend:9000/webhook/run/abc"
        body = json.loads(kwargs["content"].decode())
        assert body["status"] == "AC"
        assert body["std_out"] == "1\n"
        assert body["test_index"] == 0


class TestStreamBatchVerdicts:
    def test_posts_partials_then_complete(self):
        mock_client = _mock_client()
        with patch.object(http_callback, 'httpx') as mock_httpx, \
             patch.object(http_callback, 'INTERNAL_API_URL', 'http://backend:9000'), \
             patch.object(http_callback, 'WEBHOOK_SECRET', ''):
            mock_httpx.Client.return_value = mock_client
            http_callback.stream_batch_verdicts("batch-1", iter([
                {"test_index": 0, "status": "AC", "std_out": "1", "time_ms": 1.0, "mem_mb": 2.0},
                {"test_index": 1, "status": "WA", "std_out": "0", "time_ms": 2.0, "mem_mb": 3.0},
            ]))

        assert mock_client.post.call_count == 3
        bodies = [json.loads(c.kwargs["content"].decode()) for c in mock_client.post.call_args_list]
        assert bodies[0]["_close_after"] is False
        assert bodies[1]["status"] == "WA"
        assert bodies[2] == {"_batch_complete": True, "count": 2}
