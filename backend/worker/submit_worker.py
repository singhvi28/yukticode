import sys
import os
import asyncio
import logging
import msgpack
import httpx
import aio_pika

# Ensure server package is importable for shared config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Judger import judger
from server.config import SUBMIT_QUEUE, DLX_EXCHANGE, DLX_SUBMIT_QUEUE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
CALLBACK_TIMEOUT = 10      # seconds per attempt
MAX_RETRIES = 3

async def send_callback(url: str, payload: dict, max_retries: int = MAX_RETRIES):
    """
    POST the judging result to the callback URL asynchronously using httpx.
    """
    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=CALLBACK_TIMEOUT) as client:
                resp = await client.post(url, json=payload, headers={'Content-Type': 'application/json'})
                resp.raise_for_status()
            logger.info("Callback delivered to %s (attempt %d)", url, attempt)
            return
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            logger.warning("Callback attempt %d/%d failed: %s", attempt, max_retries, exc)
            if attempt < max_retries:
                await asyncio.sleep(2 ** (attempt - 1))
            else:
                raise

async def submit_callback(message: aio_pika.abc.AbstractIncomingMessage):
    async with message.process(requeue=False):
        data = msgpack.unpackb(message.body)

        language = data["language"]
        time_limit = data["time_limit"]
        memory_limit = data["memory_limit"]
        src_code = data["src_code"]
        test_cases = data.get("test_cases", [])
        callback_url = data["callback_url"]

        logger.info("Submit worker processing: language=%s, cases=%s, callback=%s", language, len(test_cases), callback_url)

        try:
            # 🐛 FIX: Run the blocking judger logic in a thread pool executor.
            # This prevents TLE/long-running code from blocking the async event loop,
            # allowing RabbitMQ heartbeats to continue firing in the background.
            loop = asyncio.get_running_loop()
            judge_result = await loop.run_in_executor(
                None, 
                lambda: judger.run_judger(
                    language=language,
                    time_limit=time_limit,
                    memory_limit=memory_limit,
                    src_code=src_code,
                    test_cases=test_cases,
                )
            )
        except Exception:
            logger.exception("Unexpected exception from run_judger — defaulting to SYSTEM_ERROR")
            judge_result = {"verdict": "SYSTEM_ERROR", "execution_time_ms": 0.0, "peak_memory_mb": 0.0}

        verdict = judge_result.get("verdict", "SYSTEM_ERROR")
        execution_time_ms = judge_result.get("execution_time_ms", 0.0)
        peak_memory_mb = judge_result.get("peak_memory_mb", 0.0)
        message = judge_result.get("message", "")

        logger.info("Verdict: %s (%.1fms, %.1fMB) — sending callback to %s",
                    verdict, execution_time_ms, peak_memory_mb, callback_url)

        # Fire the callback in the background so the message is acked immediately
        # and the worker can start processing the next submission.
        # The result is safe in Redis cache + DB even if the callback ultimately fails.
        asyncio.create_task(_fire_callback(callback_url, verdict, execution_time_ms, peak_memory_mb, message))


async def _fire_callback(callback_url: str, verdict: str, execution_time_ms: float, peak_memory_mb: float, message: str = ""):
    """Best-effort background delivery of the webhook callback."""
    try:
        await send_callback(callback_url, {
            "status": verdict,
            "execution_time_ms": execution_time_ms,
            "peak_memory_mb": peak_memory_mb,
            "message": message,
        })
    except Exception:
        logger.exception(
            "Callback permanently failed after %d retries for %s (result is cached in Redis + DB)",
            MAX_RETRIES, callback_url,
        )

async def main():
    logger.info(f"Connecting to RabbitMQ at {RABBITMQ_HOST}...")
    connection = await aio_pika.connect_robust(f"amqp://{RABBITMQ_HOST}/")
    
    async with connection:
        channel = await connection.channel()
        # Prefetch count ensures we don't pull all messages at once
        await channel.set_qos(prefetch_count=1)
        
        queue = await channel.declare_queue(
            SUBMIT_QUEUE,
            durable=False,
            arguments={
                'x-dead-letter-exchange': DLX_EXCHANGE,
                'x-dead-letter-routing-key': DLX_SUBMIT_QUEUE,
            }
        )
        logger.info(f"Worker listening on queue: {SUBMIT_QUEUE}")
        
        await queue.consume(submit_callback)
        
        # Keep the event loop running
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())