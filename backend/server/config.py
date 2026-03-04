# RabbitMQ connection parameters
RABBITMQ_HOST = 'localhost'

RUN_EXCHANGE = 'run_exchange'
SUBMIT_EXCHANGE = 'submit_exchange'

RUN_ROUTING_KEY = 'run_queue_key'
SUBMIT_ROUTING_KEY = 'submit_queue_key'

RUN_QUEUE = 'run_queue_v2'
SUBMIT_QUEUE = 'submit_queue_v2'

# Dead Letter Exchange (DLX) — receives messages rejected by workers after exhausting retries
DLX_EXCHANGE = 'dlx_exchange'
DLX_RUN_QUEUE = 'dlx_run_queue'
DLX_SUBMIT_QUEUE = 'dlx_submit_queue'

# Database Configuration
# In production, these should be loaded from environment variables (e.g. os.getenv(...))
DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/cfclone"
