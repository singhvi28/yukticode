"""
Regression tests for Bug 2 — asyncio.run() inside synchronous pika callback.

The original send_callback was async and the callback called asyncio.run(send_callback(...)).
Inside a pika BlockingConnection callback this raises:
    RuntimeError: This event loop is already running.

The fix replaces the async function with a synchronous one using httpx.Client.

These tests verify:
  - send_callback is a plain (non-coroutine) function — not async.
  - send_callback uses httpx.Client (sync), NOT httpx.AsyncClient.
  - The callback functions (submit_callback, run_callback) do NOT call asyncio.run().
"""
import sys
import os
import types
import asyncio
import inspect
from unittest.mock import patch, MagicMock

import pytest


def _fresh_import(module_name: str):
    """Import worker module with pika/messaging mocked, always fresh."""
    for key in list(sys.modules):
        if key in ('submit_worker', 'run_worker'):
            del sys.modules[key]

    mock_pika = MagicMock()
    mock_msg = types.ModuleType('messaging')
    mock_msg.RabbitMQConsumer = MagicMock()

    with patch.dict('sys.modules', {'pika': mock_pika, 'messaging': mock_msg}):
        mod = __import__(module_name)
    return mod


class TestSendCallbackIsSync:
    """send_callback must be a regular function, not a coroutine function."""

    def test_submit_worker_send_callback_is_not_coroutine(self):
        sw = _fresh_import('submit_worker')
        assert not inspect.iscoroutinefunction(sw.send_callback), (
            "send_callback must be a synchronous function. "
            "Calling asyncio.run() from inside a pika callback raises RuntimeError "
            "because pika's event loop is already running."
        )

    def test_run_worker_send_callback_is_not_coroutine(self):
        rw = _fresh_import('run_worker')
        assert not inspect.iscoroutinefunction(rw.send_callback), (
            "send_callback must be a synchronous function in run_worker too."
        )

    def test_submit_callback_is_not_coroutine(self):
        sw = _fresh_import('submit_worker')
        assert not inspect.iscoroutinefunction(sw.submit_callback), (
            "submit_callback is passed to pika as on_message_callback — "
            "it must be a plain function, not async."
        )

    def test_run_callback_is_not_coroutine(self):
        rw = _fresh_import('run_worker')
        assert not inspect.iscoroutinefunction(rw.run_callback), (
            "run_callback must be a plain function, not async."
        )


class TestSendCallbackUsesSyncHttpx:
    """send_callback must use httpx.Client (blocking), not httpx.AsyncClient."""

    def test_submit_worker_uses_httpx_client_not_async_client(self):
        sw = _fresh_import('submit_worker')

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch('httpx.Client') as mock_sync_client, \
             patch('httpx.AsyncClient') as mock_async_client:

            instance = MagicMock()
            instance.post = MagicMock(return_value=mock_response)
            mock_sync_client.return_value.__enter__ = MagicMock(return_value=instance)
            mock_sync_client.return_value.__exit__ = MagicMock(return_value=False)

            sw.send_callback("http://example.com/cb", {"status": "AC"}, max_retries=1)

        mock_sync_client.assert_called(), "httpx.Client (sync) was not used"
        mock_async_client.assert_not_called(), (
            "httpx.AsyncClient must NOT be used — it requires an event loop "
            "which is incompatible with pika's blocking callback model."
        )

    def test_run_worker_uses_httpx_client_not_async_client(self):
        rw = _fresh_import('run_worker')

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch('httpx.Client') as mock_sync_client, \
             patch('httpx.AsyncClient') as mock_async_client:

            instance = MagicMock()
            instance.post = MagicMock(return_value=mock_response)
            mock_sync_client.return_value.__enter__ = MagicMock(return_value=instance)
            mock_sync_client.return_value.__exit__ = MagicMock(return_value=False)

            rw.send_callback("http://example.com/cb", {"status": "AC"}, max_retries=1)

        mock_sync_client.assert_called(), "httpx.Client (sync) was not used in run_worker"
        mock_async_client.assert_not_called()


class TestNoAsyncioRunInWorkers:
    """Verify no asyncio.run() calls happen inside the message callbacks."""

    def test_submit_callback_does_not_call_asyncio_run(self):
        import msgpack
        sw = _fresh_import('submit_worker')

        body = msgpack.packb({
            "language": "py", "time_limit": 2, "memory_limit": 256,
            "src_code": "print(1)", "test_cases": [],
            "callback_url": "http://example.com/cb",
        })
        ch = MagicMock()
        ch.basic_ack = MagicMock()
        method = MagicMock()
        method.delivery_tag = 1

        with patch.object(sw, 'judger') as mock_judger, \
             patch.object(sw, 'send_callback') as mock_send, \
             patch('asyncio.run') as mock_asyncio_run:
            mock_judger.run_judger.return_value = "AC"
            mock_send.return_value = None
            sw.submit_callback(ch, method, MagicMock(), body)

        mock_asyncio_run.assert_not_called(), (
            "asyncio.run() must not be called inside submit_callback — "
            "pika's blocking loop raises RuntimeError if it is."
        )

    def test_run_callback_does_not_call_asyncio_run(self):
        import msgpack
        rw = _fresh_import('run_worker')

        body = msgpack.packb({
            "language": "py", "time_limit": 2, "memory_limit": 256,
            "src_code": "print(1)", "std_in": "",
            "callback_url": "http://example.com/cb",
        })
        ch = MagicMock()
        ch.basic_ack = MagicMock()
        method = MagicMock()
        method.delivery_tag = 1

        with patch.object(rw, 'judger') as mock_judger, \
             patch.object(rw, 'send_callback') as mock_send, \
             patch('asyncio.run') as mock_asyncio_run:
            mock_judger.custom_run.return_value = ("AC", "output")
            mock_send.return_value = None
            rw.run_callback(ch, method, MagicMock(), body)

        mock_asyncio_run.assert_not_called(), (
            "asyncio.run() must not be called inside run_callback."
        )
