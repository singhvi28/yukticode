"""
Tests for worker/messaging.py — RabbitMQConsumer.
pika is fully mocked so no broker is required.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import patch, MagicMock, call


def _make_consumer(queue='test_queue', callback=None):
    callback = callback or MagicMock()
    with patch('worker.messaging.pika') as mock_pika:
        mock_conn = MagicMock()
        mock_channel = MagicMock()
        mock_pika.BlockingConnection.return_value = mock_conn
        mock_conn.channel.return_value = mock_channel

        from worker.messaging import RabbitMQConsumer
        consumer = RabbitMQConsumer(host='localhost', queue=queue, callback=callback)
        return consumer, mock_channel, mock_pika


class TestRabbitMQConsumerInit:
    def test_queue_declared_on_init(self):
        with patch('worker.messaging.pika') as mock_pika:
            mock_conn = MagicMock()
            mock_channel = MagicMock()
            mock_pika.BlockingConnection.return_value = mock_conn
            mock_conn.channel.return_value = mock_channel

            from worker.messaging import RabbitMQConsumer
            RabbitMQConsumer(host='localhost', queue='my_queue', callback=MagicMock())

            mock_channel.queue_declare.assert_called_once_with(queue='my_queue', passive=True)

    def test_connection_uses_provided_host(self):
        with patch('worker.messaging.pika') as mock_pika:
            mock_conn = MagicMock()
            mock_pika.BlockingConnection.return_value = mock_conn
            mock_conn.channel.return_value = MagicMock()

            from worker.messaging import RabbitMQConsumer
            RabbitMQConsumer(host='rabbitmq-server', queue='q', callback=MagicMock())

            args = mock_pika.ConnectionParameters.call_args
            assert args[0][0] == 'rabbitmq-server'

    def test_queue_attribute_set(self):
        with patch('worker.messaging.pika') as mock_pika:
            mock_conn = MagicMock()
            mock_pika.BlockingConnection.return_value = mock_conn
            mock_conn.channel.return_value = MagicMock()

            from worker.messaging import RabbitMQConsumer
            consumer = RabbitMQConsumer(host='localhost', queue='specific_queue', callback=MagicMock())
            assert consumer.queue == 'specific_queue'


class TestRabbitMQConsumerStart:
    def test_start_registers_callback(self):
        with patch('worker.messaging.pika') as mock_pika:
            mock_conn = MagicMock()
            mock_channel = MagicMock()
            mock_pika.BlockingConnection.return_value = mock_conn
            mock_conn.channel.return_value = mock_channel

            from worker.messaging import RabbitMQConsumer
            cb = MagicMock()
            consumer = RabbitMQConsumer(host='localhost', queue='q', callback=cb)
            consumer.start()

            mock_channel.basic_consume.assert_called_once_with(
                queue='q', on_message_callback=cb, auto_ack=False
            )

    def test_start_calls_start_consuming(self):
        with patch('worker.messaging.pika') as mock_pika:
            mock_conn = MagicMock()
            mock_channel = MagicMock()
            mock_pika.BlockingConnection.return_value = mock_conn
            mock_conn.channel.return_value = mock_channel

            from worker.messaging import RabbitMQConsumer
            consumer = RabbitMQConsumer(host='localhost', queue='q', callback=MagicMock())
            consumer.start()

            mock_channel.start_consuming.assert_called_once()

    def test_auto_ack_is_false(self):
        """Workers must use manual ack so nack can route failed messages to DLX."""
        with patch('worker.messaging.pika') as mock_pika:
            mock_conn = MagicMock()
            mock_channel = MagicMock()
            mock_pika.BlockingConnection.return_value = mock_conn
            mock_conn.channel.return_value = mock_channel

            from worker.messaging import RabbitMQConsumer
            consumer = RabbitMQConsumer(host='localhost', queue='q', callback=MagicMock())
            consumer.start()

            _, kwargs = mock_channel.basic_consume.call_args
            assert kwargs.get('auto_ack') is False
