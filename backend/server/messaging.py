import msgpack
import aio_pika
from .config import (
    RABBITMQ_HOST,
    RUN_EXCHANGE, SUBMIT_EXCHANGE,
    RUN_ROUTING_KEY, SUBMIT_ROUTING_KEY,
    RUN_QUEUE, SUBMIT_QUEUE,
    DLX_EXCHANGE, DLX_RUN_QUEUE, DLX_SUBMIT_QUEUE,
)


class RabbitMQClient:
    """
    Manages the async RabbitMQ connection, exchange/queue declarations, and message publishing.
    Maintains a robust, persistent connection and a single channel.
    Declares a Dead Letter Exchange (DLX) so rejected messages are automatically routed there.
    """

    def __init__(self):
        self.connection = None
        self.channel = None

    async def connect(self):
        """
        Establish the connection, open a channel, and declare the exchanges and queues.
        Main queues are bound to the DLX so nack'd messages are automatically forwarded.
        This should be called on application startup.
        """
        if self.connection:
            return

        print(" [*] Connecting to RabbitMQ...")
        self.connection = await aio_pika.connect_robust(f"amqp://{RABBITMQ_HOST}/")
        self.channel = await self.connection.channel()

        # --- Dead Letter Exchange ---
        dlx = await self.channel.declare_exchange(DLX_EXCHANGE, aio_pika.ExchangeType.DIRECT)

        dlx_run_queue = await self.channel.declare_queue(DLX_RUN_QUEUE)
        dlx_submit_queue = await self.channel.declare_queue(DLX_SUBMIT_QUEUE)

        await dlx_run_queue.bind(dlx, routing_key=DLX_RUN_QUEUE)
        await dlx_submit_queue.bind(dlx, routing_key=DLX_SUBMIT_QUEUE)

        # --- Main Exchanges ---
        run_exchange = await self.channel.declare_exchange(RUN_EXCHANGE, aio_pika.ExchangeType.DIRECT)
        submit_exchange = await self.channel.declare_exchange(SUBMIT_EXCHANGE, aio_pika.ExchangeType.DIRECT)

        # --- Main Queues (with DLX forwarding on rejection) ---
        run_queue = await self.channel.declare_queue(
            RUN_QUEUE,
            arguments={
                'x-dead-letter-exchange': DLX_EXCHANGE,
                'x-dead-letter-routing-key': DLX_RUN_QUEUE,
            }
        )
        submit_queue = await self.channel.declare_queue(
            SUBMIT_QUEUE,
            arguments={
                'x-dead-letter-exchange': DLX_EXCHANGE,
                'x-dead-letter-routing-key': DLX_SUBMIT_QUEUE,
            }
        )

        await run_queue.bind(run_exchange, routing_key=RUN_ROUTING_KEY)
        await submit_queue.bind(submit_exchange, routing_key=SUBMIT_ROUTING_KEY)

        print(" [*] RabbitMQ connected and infrastructure declared (with DLX).")

    async def close(self):
        """Close the connection. Should be called on application shutdown."""
        if self.connection:
            await self.connection.close()
            self.connection = None
            self.channel = None
            print(" [*] RabbitMQ connection closed.")

    async def publish_message(self, exchange_name: str, routing_key: str, body: dict):
        """Publish a message asynchronously using msgpack."""
        if not self.channel:
            raise RuntimeError("RabbitMQ channel not open. Call connect() first.")

        message = aio_pika.Message(
            body=msgpack.packb(body),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT
        )

        exchange = await self.channel.get_exchange(exchange_name)
        await exchange.publish(message, routing_key=routing_key)
        print(f" [x] Sent message to {exchange_name} with routing key '{routing_key}'")
