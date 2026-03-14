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
from server.config import RUN_QUEUE, DLX_EXCHANGE, DLX_RUN_QUEUE

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

async def run_callback(message: aio_pika.abc.AbstractIncomingMessage):
    async with message.process(requeue=False):
        data = msgpack.unpackb(message.body)

        language = data["language"]
        callback_url = data["callback_url"]

        # ──── Batch mode: multiple tests in one container lifecycle ────
        if data.get("batch"):
            tests = data.get("tests", [])
            logger.info("Batch run: language=%s, tests=%d, callback=%s", language, len(tests), callback_url)

            results = []
            loop = asyncio.get_running_loop()

            for i, tc in enumerate(tests):
                try:
                    judge_dict = await loop.run_in_executor(
                        None,
                        lambda tc=tc: judger.custom_run(
                            language=language,
                            time_limit=data["time_limit"],
                            memory_limit=data["memory_limit"],
                            src_code=data["src_code"],
                            std_in=tc.get("input", " "),
                        )
                    )
                except Exception:
                    logger.exception("Batch test %d failed", i)
                    judge_dict = {"verdict": "SYSTEM_ERROR", "output": "", "execution_time_ms": 0.0, "peak_memory_mb": 0.0}

                results.append({
                    "status": judge_dict["verdict"],
                    "std_out": judge_dict.get("output", ""),
                    "message": judge_dict.get("message", ""),
                    "execution_time_ms": judge_dict.get("execution_time_ms", 0.0),
                    "peak_memory_mb": judge_dict.get("peak_memory_mb", 0.0),
                })

            logger.info("Batch complete — sending %d results to %s", len(results), callback_url)
            asyncio.create_task(_fire_batch_callback(callback_url, results))
            return

        # ──── Single test mode (legacy /run) ────
        logger.info("Run worker processing: language=%s, callback=%s", language, callback_url)

        try:
            loop = asyncio.get_running_loop()
            judge_dict = await loop.run_in_executor(
                None,
                lambda: judger.custom_run(
                    language=language,
                    time_limit=data["time_limit"],
                    memory_limit=data["memory_limit"],
                    src_code=data["src_code"],
                    std_in=data["std_in"],
                )
            )
        except Exception:
            logger.exception("Unexpected exception from custom_run — defaulting to SYSTEM_ERROR")
            judge_dict = {
                "verdict": "SYSTEM_ERROR", 
                "output": "", 
                "execution_time_ms": 0.0, 
                "peak_memory_mb": 0.0
            }

        logger.info("Verdict: %s — sending callback to %s", judge_dict["verdict"], callback_url)

        # Fire the callback in the background so the message is acked immediately
        asyncio.create_task(_fire_callback(callback_url, judge_dict))


async def _fire_batch_callback(callback_url: str, results: list):
    """Best-effort delivery of batched results."""
    try:
        await send_callback(callback_url, {"results": results})
    except Exception:
        logger.exception(
            "Batch callback permanently failed after %d retries for %s",
            MAX_RETRIES, callback_url,
        )


async def _fire_callback(callback_url: str, judge_dict: dict):
    """Best-effort background delivery of the webhook callback."""
    try:
        await send_callback(callback_url, {
            "status": judge_dict["verdict"],
            "std_out": judge_dict.get("output", ""),
            "message": judge_dict.get("message", ""),
            "execution_time_ms": judge_dict.get("execution_time_ms", 0.0),
            "peak_memory_mb": judge_dict.get("peak_memory_mb", 0.0)
        })
    except Exception:
        logger.exception(
            "Callback permanently failed after %d retries for %s (result is cached in Redis)",
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
            RUN_QUEUE,
            durable=False,
            arguments={
                'x-dead-letter-exchange': DLX_EXCHANGE,
                'x-dead-letter-routing-key': DLX_RUN_QUEUE,
            }
        )
        logger.info(f"Worker listening on queue: {RUN_QUEUE}")
        
        await queue.consume(run_callback)
        
        # Keep the event loop running
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())