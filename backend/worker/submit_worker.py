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
from server.config import SUBMIT_QUEUE, DLX_EXCHANGE, DLX_SUBMIT_QUEUE
from server.blob_storage import download_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/cfclone"
)
GRPC_BACKEND = os.getenv('GRPC_BACKEND', 'backend:50051')
CALLBACK_TIMEOUT = 10      # seconds per attempt
MAX_RETRIES = 3


async def fetch_submission_data(submission_id: int) -> dict | None:
    """
    Fetch source code (from blob storage) and test cases (from DB)
    for the given submission ID.

    Returns a dict with keys: src_code, test_cases, language, time_limit, memory_limit
    Returns None if the submission or problem version is not found.
    """
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy.future import select
    from server.db.models import Submission, ProblemVersion, TestCase

    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with Session() as session:
            # Fetch the submission
            stmt = select(Submission).where(Submission.id == submission_id)
            result = await session.execute(stmt)
            submission = result.scalars().first()

            if not submission:
                logger.error("Submission %d not found in DB", submission_id)
                return None

            # Fetch the problem version for limits
            stmt_pv = select(ProblemVersion).where(ProblemVersion.id == submission.problem_version_id)
            result_pv = await session.execute(stmt_pv)
            pv = result_pv.scalars().first()

            if not pv:
                logger.error("ProblemVersion for submission %d not found", submission_id)
                return None

            # Fetch test cases
            stmt_tc = select(TestCase).where(TestCase.problem_version_id == pv.id)
            result_tc = await session.execute(stmt_tc)
            test_cases_rows = result_tc.scalars().all()

            # Download source code from blob storage
            # code_url stores the object name; bucket is "submissions"
            object_name = submission.code_url.split("/")[-1] if "/" in submission.code_url else submission.code_url
            src_code = download_text("submissions", object_name)

            return {
                "language": submission.language,
                "time_limit": pv.time_limit_ms,
                "memory_limit": pv.memory_limit_mb,
                "src_code": src_code or "",
                "test_cases": [
                    {"input": tc.input_data, "expected_output": tc.expected_output}
                    for tc in test_cases_rows
                ],
            }
    finally:
        await engine.dispose()


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

        submission_id = data["submission_id"]
        language = data["language"]
        time_limit = data["time_limit"]
        memory_limit = data["memory_limit"]
        callback_url = data["callback_url"]

        logger.info("Submit worker processing: submission_id=%s, language=%s", submission_id, language)

        # Fetch src_code and test_cases from DB/blob storage (MQ Message Bloat fix)
        submission_data = await fetch_submission_data(submission_id)

        if not submission_data:
            logger.error("Could not fetch data for submission %d — sending SYSTEM_ERROR", submission_id)
            judge_result = {"verdict": "SYSTEM_ERROR", "execution_time_ms": 0.0, "peak_memory_mb": 0.0}
        else:
            src_code = submission_data["src_code"]
            test_cases = submission_data["test_cases"]

            try:
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

        logger.info("Verdict: %s (%.1fms, %.1fMB) — sending via gRPC to %s",
                    verdict, execution_time_ms, peak_memory_mb, GRPC_BACKEND)

        req = judger_pb2.SubmitVerdictRequest(
            submission_id=str(submission_id),
            status=verdict,
            execution_time_ms=execution_time_ms,
            peak_memory_mb=peak_memory_mb,
        )
        channel = grpc.aio.insecure_channel(GRPC_BACKEND)
        try:
            stub = judger_pb2_grpc.JudgeCoordinatorStub(channel)
            await stub.ReportSubmitVerdict(req)
            logger.info("Submit verdict delivered via gRPC")
        except grpc.aio.AioRpcError as e:
            logger.error("gRPC ReportSubmitVerdict failed: %s — falling back to HTTP", e)
            asyncio.create_task(_fire_callback(
                callback_url, verdict, execution_time_ms, peak_memory_mb,
                judge_result.get("message", "")
            ))
        finally:
            await channel.close()


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