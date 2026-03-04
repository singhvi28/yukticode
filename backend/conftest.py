"""
conftest.py — shared pytest fixtures and path configuration.
Adds the project root to sys.path so all imports resolve correctly regardless
of which directory pytest is invoked from.
"""
import sys
import os

# Ensure the project root is always on sys.path
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Ensure the worker directory is also on sys.path (workers use non-relative imports
# like `from Judger import judger` and `from messaging import RabbitMQConsumer`)
WORKER_DIR = os.path.join(ROOT, 'worker')
if WORKER_DIR not in sys.path:
    sys.path.insert(0, WORKER_DIR)

from unittest.mock import MagicMock

# Stub ``pika`` at import time so worker modules never attempt a real TCP
# connection to RabbitMQ when they are imported during test collection.
# Individual tests can still ``patch('worker.messaging.pika')`` to configure
# specific return values.
sys.modules.setdefault('pika', MagicMock())
