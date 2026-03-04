import asyncio
import logging
import msgpack
import httpx
from Judger import judger
from messaging import RabbitMQConsumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

RABBITMQ_HOST = 'localhost'
SUBMIT_QUEUE = 'submit_queue'
CALLBACK_TIMEOUT = 10      # seconds per attempt
MAX_RETRIES = 3


async def send_callback(url: str, payload: dict, max_retries: int = MAX_RETRIES):
    """
    POST the judging result to the callback URL using httpx.
    Retries up to max_retries times with exponential backoff.
    Raises httpx.HTTPError on final failure.
    """
    async with httpx.AsyncClient(timeout=CALLBACK_TIMEOUT) as client:
        for attempt in range(1, max_retries + 1):
            try:
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


def submit_callback(ch, method, properties, body):
    data = msgpack.unpackb(body)

    language = data["language"]
    time_limit = data["time_limit"]
    memory_limit = data["memory_limit"]
    src_code = data["src_code"]
    std_in = data["std_in"]
    expected_out = data["expected_out"]
    callback_url = data["callback_url"]

    logger.info("Submit worker processing: language=%s, callback=%s", language, callback_url)

    try:
        judge_result = judger.run_judger(
            language=language,
            time_limit=time_limit,
            memory_limit=memory_limit,
            src_code=src_code,
            std_in=std_in,
            expected_out=expected_out,
        )
    except Exception:
        # run_judger is designed never to raise, but be defensive
        logger.exception("Unexpected exception from run_judger — defaulting to SYSTEM_ERROR")
        judge_result = "SYSTEM_ERROR"

    logger.info("Verdict: %s — sending callback to %s", judge_result, callback_url)

    try:
        asyncio.run(send_callback(callback_url, {"status": judge_result}))
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception:
        logger.exception(
            "Callback permanently failed after %d retries for %s — sending to DLX",
            MAX_RETRIES, callback_url,
        )
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


if __name__ == "__main__":
    consumer = RabbitMQConsumer(host=RABBITMQ_HOST, queue=SUBMIT_QUEUE, callback=submit_callback)
    consumer.start()