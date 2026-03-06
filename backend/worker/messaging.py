import pika


class RabbitMQConsumer:
    """
    Shared RabbitMQ consumer setup for workers. Manages connection, queue declaration,
    and message consumption with manual acknowledgement support.
    """

    def __init__(self, host: str, queue: str, callback):
        """
        Parameters:
        - host (str): RabbitMQ host address.
        - queue (str): Queue name to consume from.
        - callback (callable): on_message_callback for basic_consume.
                               Signature: callback(ch, method, properties, body)
        """
        self.queue = queue
        self.callback = callback

        connection = pika.BlockingConnection(pika.ConnectionParameters(host))
        self.channel = connection.channel()
        self.channel.queue_declare(queue=queue, passive=True)
        # Limit to one unacknowledged message at a time per worker so that
        # a slow callback does not block the *other* worker processes.
        self.channel.basic_qos(prefetch_count=1)

    def start(self):
        """Start consuming messages from the queue (manual ack mode)."""
        self.channel.basic_consume(
            queue=self.queue,
            on_message_callback=self.callback,
            auto_ack=False,   # Workers call basic_ack / basic_nack explicitly
        )
        print(f' [*] Worker waiting for messages on queue: {self.queue}...')
        self.channel.start_consuming()
