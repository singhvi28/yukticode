"""
Tests for server/messaging.py — RabbitMQClient using aio-pika.
All calls to aio_pika are mocked so no broker is required.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import patch, MagicMock, AsyncMock, call
import msgpack
from server.messaging import RabbitMQClient


@pytest.fixture
def mock_aio_pika():
    with patch('server.messaging.aio_pika') as mock_pika:
        # Override the MagicMock from conftest.py with actual AsyncMocks
        mock_conn = AsyncMock()
        mock_pika.connect_robust = AsyncMock(return_value=mock_conn)
        
        mock_channel = AsyncMock()
        mock_conn.channel = AsyncMock(return_value=mock_channel)
        
        mock_exchange = AsyncMock()
        mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
        mock_channel.get_exchange = AsyncMock(return_value=mock_exchange)
        
        mock_queue = AsyncMock()
        mock_channel.declare_queue = AsyncMock(return_value=mock_queue)

        yield mock_pika, mock_conn, mock_channel, mock_exchange, mock_queue


class TestRabbitMQClientConnect:
    @pytest.mark.asyncio
    async def test_connection_opened(self, mock_aio_pika):
        mock_pika, mock_conn, mock_channel, _, _ = mock_aio_pika
        
        client = RabbitMQClient()
        await client.connect()
        
        mock_pika.connect_robust.assert_called_once()
        mock_conn.channel.assert_called_once()

    @pytest.mark.asyncio
    async def test_exchanges_declared(self, mock_aio_pika):
        _, _, mock_channel, _, _ = mock_aio_pika
        
        client = RabbitMQClient()
        await client.connect()
        
        # DLX exchange (1) + run exchange (1) + submit exchange (1) = 3
        assert mock_channel.declare_exchange.call_count == 3

    @pytest.mark.asyncio
    async def test_queues_declared(self, mock_aio_pika):
        _, _, mock_channel, _, _ = mock_aio_pika
        
        client = RabbitMQClient()
        await client.connect()
        
        # DLX run queue (1) + DLX submit queue (1) + run queue (1) + submit queue (1) = 4
        assert mock_channel.declare_queue.call_count == 4

    @pytest.mark.asyncio
    async def test_queues_bound(self, mock_aio_pika):
        _, _, _, _, mock_queue = mock_aio_pika
        
        client = RabbitMQClient()
        await client.connect()
        
        # dlx_run (1) + dlx_submit (1) + run_queue (1) + submit_queue (1) = 4
        assert mock_queue.bind.call_count == 4

    @pytest.mark.asyncio
    async def test_connect_is_idempotent(self, mock_aio_pika):
        mock_pika, _, _, _, _ = mock_aio_pika
        
        client = RabbitMQClient()
        await client.connect()
        await client.connect()  # second call
        
        # connect_robust should still only be called once
        mock_pika.connect_robust.assert_called_once()


class TestRabbitMQClientClose:
    @pytest.mark.asyncio
    async def test_close_shuts_down_connection(self, mock_aio_pika):
        _, mock_conn, _, _, _ = mock_aio_pika
        
        client = RabbitMQClient()
        await client.connect()
        await client.close()
        
        mock_conn.close.assert_called_once()
        assert client.connection is None
        assert client.channel is None

    @pytest.mark.asyncio
    async def test_close_is_safe_when_not_connected(self):
        client = RabbitMQClient()
        await client.close()  # Should not raise


class TestRabbitMQClientPublish:
    @pytest.mark.asyncio
    async def test_publish_encodes_with_msgpack(self, mock_aio_pika):
        mock_pika, _, _, mock_exchange, _ = mock_aio_pika
        
        client = RabbitMQClient()
        await client.connect()
        
        body = {"language": "cpp", "time_limit": 2}
        await client.publish_message("test_exchange", "test_key", body)
        
        # Verify aio_pika.Message was created correctly
        args, kwargs = mock_pika.Message.call_args
        actual_body = kwargs.get('body')
        assert msgpack.unpackb(actual_body) == body
        
        # Verify publish was called on exchange
        mock_exchange.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_raises_if_not_connected(self):
        client = RabbitMQClient()
        with pytest.raises(RuntimeError, match="RabbitMQ channel not open"):
            await client.publish_message("ex", "key", {"x": 1})
