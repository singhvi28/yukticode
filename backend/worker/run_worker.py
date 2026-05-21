import sys
import os
import asyncio
import logging
import msgpack
import aio_pika

# Ensure server package is importable for shared config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Judger import judger
from http_callback import report_run_verdict, stream_batch_verdicts
from server.config import RUN_QUEUE, DLX_EXCHANGE, DLX_RUN_QUEUE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
for _noisy in ("aiormq", "aio_pika", "urllib3", "docker"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')


async def run_callback(message: aio_pika.abc.AbstractIncomingMessage):
    async with message.process(requeue=False):
        data = msgpack.unpackb(message.body)

        language = data["language"]

        # ──── Batch mode ────
        if data.get("batch"):
            batch_id = data["batch_id"]
            tests = data.get("tests", [])
            logger.info("Batch run: language=%s, tests=%d, batch_id=%s", language, len(tests), batch_id)

            def _judge_batch():
                """Synchronous generator — one container, compile once."""
                for i, res in enumerate(
                    judger.custom_run_batch(
                        language=language,
                        time_limit=data["time_limit"],
                        memory_limit=data["memory_limit"],
                        src_code=data["src_code"],
                        tests=tests,
                    )
                ):
                    verdict = res.get("verdict", "SYSTEM_ERROR")
                    expected_output = tests[i].get("expected_output") if i < len(tests) else None
                    if verdict == "AC" and expected_output is not None:
                        if not judger.compare_outputs(expected_output, res.get("output", "")):
                            verdict = "WA"

                    yield {
                        "test_index": i,
                        "status": verdict,
                        "std_out": res.get("output", ""),
                        "time_ms": res.get("execution_time_ms", 0.0),
                        "mem_mb": res.get("peak_memory_mb", 0.0),
                    }

            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    None,
                    lambda: stream_batch_verdicts(batch_id, _judge_batch())
                )
                logger.info("Batch complete — posted %d results via webhook for batch_id=%s", len(tests), batch_id)
            except Exception:
                logger.exception("Webhook stream_batch_verdicts failed for batch_id=%s", batch_id)
            return

        # ──── Single run mode ────
        run_id = data["run_id"]
        logger.info("Run worker processing: language=%s, run_id=%s", language, run_id)

        try:
            loop = asyncio.get_running_loop()
            judge_dict = await loop.run_in_executor(
                None,
                lambda: judger.custom_run(
                    language=language,
                    time_limit=data["time_limit"],
                    memory_limit=data["memory_limit"],
                    src_code=data["src_code"],
                    std_in=data.get("std_in", " "),
                )
            )
        except Exception:
            logger.exception("Unexpected exception from custom_run — defaulting to SYSTEM_ERROR")
            judge_dict = {"verdict": "SYSTEM_ERROR", "output": "", "execution_time_ms": 0.0, "peak_memory_mb": 0.0}

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: report_run_verdict(
                    run_id=run_id,
                    status=judge_dict.get("verdict", "SYSTEM_ERROR"),
                    std_out=judge_dict.get("output", ""),
                    time_ms=judge_dict.get("execution_time_ms", 0.0),
                    mem_mb=judge_dict.get("peak_memory_mb", 0.0),
                )
            )
            logger.info("Run verdict: %s delivered via webhook for run_id=%s", judge_dict.get("verdict"), run_id)
        except Exception:
            logger.exception("Webhook report_run_verdict failed for run_id=%s", run_id)


async def main():
    logger.info("Connecting to RabbitMQ at %s...", RABBITMQ_HOST)
    connection = await aio_pika.connect_robust(f"amqp://{RABBITMQ_HOST}/")

    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=1)

        queue = await channel.declare_queue(
            RUN_QUEUE,
            durable=False,
            arguments={
                'x-dead-letter-exchange': DLX_EXCHANGE,
                'x-dead-letter-routing-key': DLX_RUN_QUEUE,
            }
        )
        logger.info("Worker listening on queue: %s", RUN_QUEUE)
        await queue.consume(run_callback)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())