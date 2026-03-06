"""
Regression tests for Bug 1 & Bug 4 (queue name consistency).

Bug 1: Workers hardcoded 'submit_queue' / 'run_queue' while the server config
       used 'submit_queue_v2' / 'run_queue_v2'. Messages were silently dropped.

Bug 4: Worker's RabbitMQConsumer redeclared queues without DLX arguments,
       causing RabbitMQ PRECONDITION_FAILED at startup.

These tests verify that:
  - The queue names used by workers match the server config exactly.
  - The worker consumer uses passive=True on queue_declare (no re-declaration).
"""
import sys
import os
import types
from unittest.mock import patch, MagicMock, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_worker(module_name: str):
    """Import a worker module with pika/messaging fully mocked."""
    for key in list(sys.modules):
        if key in ('submit_worker', 'run_worker'):
            del sys.modules[key]

    mock_pika = MagicMock()
    mock_msg = types.ModuleType('messaging')
    mock_msg.RabbitMQConsumer = MagicMock()

    with patch.dict('sys.modules', {'pika': mock_pika, 'messaging': mock_msg}):
        mod = __import__(module_name)
    return mod


# ---------------------------------------------------------------------------
# Bug 1 — Queue names must match server.config
# ---------------------------------------------------------------------------

class TestQueueNameConsistency:
    """Workers must consume from the exact same queues the server publishes to."""

    def test_submit_worker_queue_matches_server_config(self):
        from server.config import SUBMIT_QUEUE as SERVER_SUBMIT_QUEUE

        mod = _import_worker('submit_worker')
        # The worker should not define its own SUBMIT_QUEUE constant at all
        # (it must import from server.config), OR if it does define one it
        # must equal the server value.
        worker_queue = getattr(mod, 'SUBMIT_QUEUE', None)
        if worker_queue is not None:
            assert worker_queue == SERVER_SUBMIT_QUEUE, (
                f"Worker SUBMIT_QUEUE={worker_queue!r} doesn't match "
                f"server SUBMIT_QUEUE={SERVER_SUBMIT_QUEUE!r}"
            )

    def test_run_worker_queue_matches_server_config(self):
        from server.config import RUN_QUEUE as SERVER_RUN_QUEUE

        mod = _import_worker('run_worker')
        worker_queue = getattr(mod, 'RUN_QUEUE', None)
        if worker_queue is not None:
            assert worker_queue == SERVER_RUN_QUEUE, (
                f"Worker RUN_QUEUE={worker_queue!r} doesn't match "
                f"server RUN_QUEUE={SERVER_RUN_QUEUE!r}"
            )

    def test_submit_worker_consumer_started_with_correct_queue(self):
        """RabbitMQConsumer must be instantiated with the server-config queue name."""
        from server.config import SUBMIT_QUEUE as SERVER_SUBMIT_QUEUE

        mock_pika = MagicMock()
        mock_msg = types.ModuleType('messaging')
        captured = {}

        class CapturingConsumer:
            def __init__(self, host, queue, callback):
                captured['queue'] = queue
            def start(self):
                pass

        mock_msg.RabbitMQConsumer = CapturingConsumer

        for key in list(sys.modules):
            if key == 'submit_worker':
                del sys.modules[key]

        with patch.dict('sys.modules', {'pika': mock_pika, 'messaging': mock_msg}):
            import submit_worker
            # Simulate the __main__ block without actually running it
            consumer = CapturingConsumer(
                host='localhost',
                queue=submit_worker.SUBMIT_QUEUE,
                callback=submit_worker.submit_callback,
            )

        assert captured['queue'] == SERVER_SUBMIT_QUEUE, (
            f"submit_worker would start consumer on {captured['queue']!r}, "
            f"but server publishes to {SERVER_SUBMIT_QUEUE!r}"
        )

    def test_run_worker_consumer_started_with_correct_queue(self):
        """RabbitMQConsumer must be instantiated with the server-config queue name."""
        from server.config import RUN_QUEUE as SERVER_RUN_QUEUE

        mock_pika = MagicMock()
        mock_msg = types.ModuleType('messaging')
        captured = {}

        class CapturingConsumer:
            def __init__(self, host, queue, callback):
                captured['queue'] = queue
            def start(self):
                pass

        mock_msg.RabbitMQConsumer = CapturingConsumer

        for key in list(sys.modules):
            if key == 'run_worker':
                del sys.modules[key]

        with patch.dict('sys.modules', {'pika': mock_pika, 'messaging': mock_msg}):
            import run_worker
            consumer = CapturingConsumer(
                host='localhost',
                queue=run_worker.RUN_QUEUE,
                callback=run_worker.run_callback,
            )

        assert captured['queue'] == SERVER_RUN_QUEUE, (
            f"run_worker would start consumer on {captured['queue']!r}, "
            f"but server publishes to {SERVER_RUN_QUEUE!r}"
        )


# ---------------------------------------------------------------------------
# Bug 4 — queue_declare must use passive=True
# ---------------------------------------------------------------------------

class TestWorkerQueueDeclarePassive:
    """
    Workers must NOT redeclare queues with different arguments.
    The server already declared them with DLX args; a plain declare would
    cause RabbitMQ PRECONDITION_FAILED and crash the worker at startup.
    """

    def test_queue_declare_called_with_passive_true(self):
        with patch('worker.messaging.pika') as mock_pika:
            mock_conn = MagicMock()
            mock_channel = MagicMock()
            mock_pika.BlockingConnection.return_value = mock_conn
            mock_conn.channel.return_value = mock_channel

            from worker.messaging import RabbitMQConsumer
            RabbitMQConsumer(host='localhost', queue='submit_queue_v2', callback=MagicMock())

        # Verify passive=True is present — without it RabbitMQ would crash
        _, kwargs = mock_channel.queue_declare.call_args
        assert kwargs.get('passive') is True, (
            "queue_declare called without passive=True — this causes "
            "PRECONDITION_FAILED when the server has already declared the "
            "queue with DLX arguments."
        )

    def test_queue_declare_does_not_include_dlx_arguments(self):
        """Workers must not pass x-dead-letter-* args — the server owns that declaration."""
        with patch('worker.messaging.pika') as mock_pika:
            mock_conn = MagicMock()
            mock_channel = MagicMock()
            mock_pika.BlockingConnection.return_value = mock_conn
            mock_conn.channel.return_value = mock_channel

            from worker.messaging import RabbitMQConsumer
            RabbitMQConsumer(host='localhost', queue='submit_queue_v2', callback=MagicMock())

        _, kwargs = mock_channel.queue_declare.call_args
        arguments = kwargs.get('arguments', {})
        assert 'x-dead-letter-exchange' not in (arguments or {}), (
            "Worker must not declare DLX args — use passive=True instead."
        )
