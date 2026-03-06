"""
Tests for the send_callback helper and ack/nack routing in workers.
All external dependencies are mocked — no real pika or HTTP connections.
"""
import sys
import os
import types
from unittest.mock import patch, MagicMock

import pytest
import time
import msgpack
import httpx


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sw():
    """
    Return a freshly-imported submit_worker module with pika and messaging
    fully mocked so no real broker connection is ever made.
    """
    mock_pika = MagicMock()
    mock_messaging_mod = types.ModuleType('messaging')
    mock_messaging_mod.RabbitMQConsumer = MagicMock()

    # Remove any cached version so we always get a clean import
    for key in list(sys.modules.keys()):
        if key in ('submit_worker', 'run_worker'):
            del sys.modules[key]

    with patch.dict('sys.modules', {'pika': mock_pika, 'messaging': mock_messaging_mod}):
        import submit_worker
        yield submit_worker

    # Clean up after the test so the cached module doesn't bleed out
    for key in ('submit_worker', 'run_worker'):
        sys.modules.pop(key, None)


# ---------------------------------------------------------------------------
# send_callback tests  (synchronous — uses httpx.Client, not AsyncClient)
# ---------------------------------------------------------------------------

class TestSendCallback:
    def test_delivers_on_first_attempt(self, sw):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch('httpx.Client') as MockClient:
            instance = MagicMock()
            instance.post = MagicMock(return_value=mock_response)
            MockClient.return_value.__enter__ = MagicMock(return_value=instance)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            sw.send_callback("http://example.com/cb", {"status": "AC"}, max_retries=3)
            instance.post.assert_called_once()

    def test_retries_on_timeout_and_succeeds(self, sw):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch('httpx.Client') as MockClient, \
             patch('time.sleep'):
            instance = MagicMock()
            instance.post = MagicMock(
                side_effect=[httpx.TimeoutException("timed out"), mock_response]
            )
            MockClient.return_value.__enter__ = MagicMock(return_value=instance)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            sw.send_callback("http://example.com/cb", {"status": "AC"}, max_retries=3)

        assert instance.post.call_count == 2

    def test_raises_after_max_retries_exhausted(self, sw):
        with patch('httpx.Client') as MockClient, \
             patch('time.sleep'):
            instance = MagicMock()
            instance.post = MagicMock(side_effect=httpx.TimeoutException("always out"))
            MockClient.return_value.__enter__ = MagicMock(return_value=instance)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(httpx.TimeoutException):
                sw.send_callback("http://example.com/cb", {"status": "AC"}, max_retries=3)

        assert instance.post.call_count == 3


# ---------------------------------------------------------------------------
# Ack / Nack routing tests
# ---------------------------------------------------------------------------

class TestSubmitCallbackAckNack:
    def _body(self):
        return msgpack.packb({
            "language": "py", "time_limit": 2, "memory_limit": 256,
            "src_code": "print(1)", "test_cases": [],
            "callback_url": "http://example.com/cb",
        })

    def test_acks_on_callback_success(self, sw):
        ch, method, props = MagicMock(), MagicMock(), MagicMock()
        method.delivery_tag = 7

        with patch.object(sw, 'judger') as mock_judger, \
             patch.object(sw, 'send_callback') as mock_send:
            mock_judger.run_judger.return_value = {"verdict": "AC", "execution_time_ms": 50.0, "peak_memory_mb": 12.0}
            mock_send.return_value = None
            sw.submit_callback(ch, method, props, self._body())

        ch.basic_ack.assert_called_once_with(delivery_tag=7)
        ch.basic_nack.assert_not_called()

    def test_nacks_on_callback_failure(self, sw):
        ch, method, props = MagicMock(), MagicMock(), MagicMock()
        method.delivery_tag = 42

        with patch.object(sw, 'judger') as mock_judger, \
             patch.object(sw, 'send_callback') as mock_send:
            mock_judger.run_judger.return_value = {"verdict": "AC", "execution_time_ms": 50.0, "peak_memory_mb": 12.0}
            mock_send.side_effect = httpx.TimeoutException("gone")
            sw.submit_callback(ch, method, props, self._body())

        ch.basic_nack.assert_called_once_with(delivery_tag=42, requeue=False)
        ch.basic_ack.assert_not_called()
