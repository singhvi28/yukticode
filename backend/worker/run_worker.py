import sys
import os
import asyncio
import logging
import msgpack
import httpx
import grpc
import aio_pika

# Ensure server package is importable for shared config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import judger_pb2
import judger_pb2_grpc
from Judger import judger
from server.config import RUN_QUEUE, DLX_EXCHANGE, DLX_RUN_QUEUE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
GRPC_BACKEND = os.getenv('GRPC_BACKEND', 'backend:50051')
CALLBACK_TIMEOUT = 10      # seconds per attempt
MAX_RETRIES = 3


async def send_callback(url: str, payload: dict, max_retries: int = MAX_RETRIES):
    """POST the judging result to the callback URL asynchronously (fallback for HTTP)."""
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
        # Extract run_id or batch_id from callback URL (e.g. http://backend:9000/webhook/run/{id})
        run_id = callback_url.rstrip("/").split("/")[-1]

        # ──── Batch mode: stream results via gRPC ────
        if data.get("batch"):
            tests = data.get("tests", [])
            logger.info("Batch run: language=%s, tests=%d, batch_id=%s", language, len(tests), run_id)

            async def result_generator():
                loop = asyncio.get_running_loop()
                for i, tc in enumerate(tests):
                    try:
                        judge_dict = await loop.run_in_executor(
                            None,
                            lambda tc=tc, d=data: judger.custom_run(
                                language=d["language"],
                                time_limit=d["time_limit"],
                                memory_limit=d["memory_limit"],
                                src_code=d["src_code"],
                                std_in=tc.get("input", " "),
                            )
                        )
                    except Exception:
                        logger.exception("Batch test %d failed", i)
                        judge_dict = {
                            "verdict": "SYSTEM_ERROR",
                            "output": "",
                            "execution_time_ms": 0.0,
                            "peak_memory_mb": 0.0,
                        }

                    yield judger_pb2.RunVerdictRequest(
                        run_id=run_id,
                        status=judge_dict.get("verdict", "SYSTEM_ERROR"),
                        std_out=judge_dict.get("output", ""),
                        execution_time_ms=judge_dict.get("execution_time_ms", 0.0),
                        peak_memory_mb=judge_dict.get("peak_memory_mb", 0.0),
                        test_index=i,
                    )

            channel = grpc.aio.insecure_channel(GRPC_BACKEND)
            try:
                stub = judger_pb2_grpc.JudgeCoordinatorStub(channel)
                await stub.StreamBatchRunVerdict(result_generator())
                logger.info("Batch complete — streamed %d results via gRPC", len(tests))
            except grpc.aio.AioRpcError as e:
                logger.error("gRPC StreamBatchRunVerdict failed: %s — falling back to HTTP", e)
                # Fallback: collect results and HTTP callback
                results = []
                loop = asyncio.get_running_loop()
                for i, tc in enumerate(tests):
                    try:
                        jd = await loop.run_in_executor(
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
                        jd = {"verdict": "SYSTEM_ERROR", "output": "", "execution_time_ms": 0.0, "peak_memory_mb": 0.0}
                    results.append({
                        "status": jd.get("verdict"),
                        "std_out": jd.get("output", ""),
                        "execution_time_ms": jd.get("execution_time_ms", 0.0),
                        "peak_memory_mb": jd.get("peak_memory_mb", 0.0),
                    })
                asyncio.create_task(_fire_batch_callback(callback_url, results))
            finally:
                await channel.close()
            return

        # ──── Single test mode: gRPC ReportRunVerdict ────
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
                    std_in=data["std_in"],
                )
            )
        except Exception:
            logger.exception("Unexpected exception from custom_run — defaulting to SYSTEM_ERROR")
            judge_dict = {
                "verdict": "SYSTEM_ERROR",
                "output": "",
                "execution_time_ms": 0.0,
                "peak_memory_mb": 0.0,
            }

        req = judger_pb2.RunVerdictRequest(
            run_id=run_id,
            status=judge_dict.get("verdict", "SYSTEM_ERROR"),
            std_out=judge_dict.get("output", ""),
            execution_time_ms=judge_dict.get("execution_time_ms", 0.0),
            peak_memory_mb=judge_dict.get("peak_memory_mb", 0.0),
            test_index=0,
        )

        channel = grpc.aio.insecure_channel(GRPC_BACKEND)
        try:
            stub = judger_pb2_grpc.JudgeCoordinatorStub(channel)
            await stub.ReportRunVerdict(req)
            logger.info("Verdict: %s — delivered via gRPC", judge_dict["verdict"])
        except grpc.aio.AioRpcError as e:
            logger.error("gRPC ReportRunVerdict failed: %s — falling back to HTTP", e)
            asyncio.create_task(_fire_callback(callback_url, judge_dict))
        finally:
            await channel.close()


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