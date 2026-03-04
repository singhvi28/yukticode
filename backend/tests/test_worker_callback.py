"""
Tests for the send_callback helper and ack/nack routing in workers.
All external dependencies are mocked — no real pika or HTTP connections.
"""
import sys
import os
import types
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import asyncio
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
# send_callback tests
# ---------------------------------------------------------------------------

class TestSendCallback:
    @pytest.mark.asyncio
    async def test_delivers_on_first_attempt(self, sw):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch('httpx.AsyncClient') as MockClient:
            instance = AsyncMock()
            instance.post = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            await sw.send_callback("http://example.com/cb", {"status": "AC"}, max_retries=3)
            instance.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retries_on_timeout_and_succeeds(self, sw):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch('httpx.AsyncClient') as MockClient:
            instance = AsyncMock()
            instance.post = AsyncMock(
                side_effect=[httpx.TimeoutException("timed out"), mock_response]
            )
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch('asyncio.sleep', new_callable=AsyncMock):
                await sw.send_callback("http://example.com/cb", {"status": "AC"}, max_retries=3)

            assert instance.post.await_count == 2

    @pytest.mark.asyncio
    async def test_raises_after_max_retries_exhausted(self, sw):
        with patch('httpx.AsyncClient') as MockClient:
            instance = AsyncMock()
            instance.post = AsyncMock(side_effect=httpx.TimeoutException("always out"))
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch('asyncio.sleep', new_callable=AsyncMock):
                with pytest.raises(httpx.TimeoutException):
                    await sw.send_callback("http://example.com/cb", {"status": "AC"}, max_retries=3)

            assert instance.post.await_count == 3


# ---------------------------------------------------------------------------
# Ack / Nack routing tests
# ---------------------------------------------------------------------------

class TestSubmitCallbackAckNack:
    def _body(self):
        return msgpack.packb({
            "language": "py", "time_limit": 2, "memory_limit": 256,
            "src_code": "print(1)", "std_in": "", "expected_out": "1",
            "callback_url": "http://example.com/cb",
        })

    def test_acks_on_callback_success(self, sw):
        ch, method, props = MagicMock(), MagicMock(), MagicMock()
        method.delivery_tag = 7

        with patch.object(sw, 'judger') as mock_judger, \
             patch.object(sw, 'send_callback', new_callable=AsyncMock) as mock_send:
            mock_judger.run_judger.return_value = "AC"
            mock_send.return_value = None
            sw.submit_callback(ch, method, props, self._body())

        ch.basic_ack.assert_called_once_with(delivery_tag=7)
        ch.basic_nack.assert_not_called()

    def test_nacks_on_callback_failure(self, sw):
        ch, method, props = MagicMock(), MagicMock(), MagicMock()
        method.delivery_tag = 42

        with patch.object(sw, 'judger') as mock_judger, \
             patch.object(sw, 'send_callback', new_callable=AsyncMock) as mock_send:
            mock_judger.run_judger.return_value = "AC"
            mock_send.side_effect = httpx.TimeoutException("gone")
            sw.submit_callback(ch, method, props, self._body())

        ch.basic_nack.assert_called_once_with(delivery_tag=42, requeue=False)
        ch.basic_ack.assert_not_called()
