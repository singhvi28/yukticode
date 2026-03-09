import sys
import os
# Ensure server package is importable for shared config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import logging
import time
import msgpack
import httpx
from Judger import judger
from messaging import RabbitMQConsumer
from server.config import RUN_QUEUE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

RABBITMQ_HOST = 'localhost'
CALLBACK_TIMEOUT = 10      # seconds per attempt
MAX_RETRIES = 3


def send_callback(url: str, payload: dict, max_retries: int = MAX_RETRIES):
    """
    POST the judging result to the callback URL using httpx (synchronous).
    Retries up to max_retries times with exponential backoff.
    Raises httpx.HTTPError on final failure.
    """
    for attempt in range(1, max_retries + 1):
        try:
            with httpx.Client(timeout=CALLBACK_TIMEOUT) as client:
                resp = client.post(url, json=payload, headers={'Content-Type': 'application/json'})
                resp.raise_for_status()
            logger.info("Callback delivered to %s (attempt %d)", url, attempt)
            return
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            logger.warning("Callback attempt %d/%d failed: %s", attempt, max_retries, exc)
            if attempt < max_retries:
                time.sleep(2 ** (attempt - 1))
            else:
                raise


def run_callback(ch, method, properties, body):
    data = msgpack.unpackb(body)

    language = data["language"]
    callback_url = data["callback_url"]

    logger.info("Run worker processing: language=%s, callback=%s", language, callback_url)

    try:
        judge_dict = judger.custom_run(
            language=language,
            time_limit=data["time_limit"],
            memory_limit=data["memory_limit"],
            src_code=data["src_code"],
            std_in=data["std_in"],
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

    try:
        send_callback(callback_url, {
            "status": judge_dict["verdict"], 
            "std_out": judge_dict.get("output", ""),
            "execution_time_ms": judge_dict.get("execution_time_ms", 0.0),
            "peak_memory_mb": judge_dict.get("peak_memory_mb", 0.0)
        })
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception:
        logger.exception(
            "Callback permanently failed after %d retries for %s — sending to DLX",
            MAX_RETRIES, callback_url,
        )
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


if __name__ == "__main__":
    consumer = RabbitMQConsumer(host=RABBITMQ_HOST, queue=RUN_QUEUE, callback=run_callback)
    consumer.start()