import sys
import os
import asyncio
import logging
import msgpack
import aio_pika

# Ensure server package is importable for shared config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Judger import judger
from grpc_client import report_submit_verdict
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


async def fetch_submission_data(submission_id: int) -> dict | None:
    """
    Fetch source code (from blob storage) and test cases (from DB)
    for the given submission ID.
    """
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy.future import select
    from server.db.models import Submission, ProblemVersion, TestCase

    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with Session() as session:
            stmt = select(Submission).where(Submission.id == submission_id)
            result = await session.execute(stmt)
            submission = result.scalars().first()

            if not submission:
                logger.error("Submission %d not found in DB", submission_id)
                return None

            stmt_pv = select(ProblemVersion).where(ProblemVersion.id == submission.problem_version_id)
            result_pv = await session.execute(stmt_pv)
            pv = result_pv.scalars().first()

            if not pv:
                logger.error("ProblemVersion for submission %d not found", submission_id)
                return None

            stmt_tc = select(TestCase).where(TestCase.problem_version_id == pv.id)
            result_tc = await session.execute(stmt_tc)
            test_cases_rows = result_tc.scalars().all()

            # code_url stores blob object name
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


async def submit_callback(message: aio_pika.abc.AbstractIncomingMessage):
    async with message.process(requeue=False):
        data = msgpack.unpackb(message.body)

        submission_id = data["submission_id"]
        language = data["language"]
        time_limit = data["time_limit"]
        memory_limit = data["memory_limit"]

        logger.info("Submit worker processing: submission_id=%s, language=%s", submission_id, language)

        # Fetch src_code and test_cases from DB/blob (MQ bloat fix)
        submission_data = await fetch_submission_data(submission_id)

        if not submission_data:
            logger.error("Could not fetch data for submission %d — sending SYSTEM_ERROR", submission_id)
            judge_result = {"verdict": "SYSTEM_ERROR", "execution_time_ms": 0.0, "peak_memory_mb": 0.0}
        else:
            try:
                loop = asyncio.get_running_loop()
                judge_result = await loop.run_in_executor(
                    None,
                    lambda: judger.run_judger(
                        language=language,
                        time_limit=time_limit,
                        memory_limit=memory_limit,
                        src_code=submission_data["src_code"],
                        test_cases=submission_data["test_cases"],
                    )
                )
            except Exception:
                logger.exception("Unexpected exception from run_judger — defaulting to SYSTEM_ERROR")
                judge_result = {"verdict": "SYSTEM_ERROR", "execution_time_ms": 0.0, "peak_memory_mb": 0.0}

        verdict = judge_result.get("verdict", "SYSTEM_ERROR")
        execution_time_ms = judge_result.get("execution_time_ms", 0.0)
        peak_memory_mb = judge_result.get("peak_memory_mb", 0.0)

        logger.info("Verdict: %s (%.1fms, %.1fMB) — reporting via gRPC", verdict, execution_time_ms, peak_memory_mb)

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: report_submit_verdict(
                    submission_id=submission_id,
                    status=verdict,
                    time_ms=execution_time_ms,
                    mem_mb=peak_memory_mb,
                )
            )
            logger.info("Submit verdict delivered via gRPC for submission %s", submission_id)
        except Exception:
            logger.exception("gRPC report_submit_verdict failed for submission %s", submission_id)


async def main():
    logger.info("Connecting to RabbitMQ at %s...", RABBITMQ_HOST)
    connection = await aio_pika.connect_robust(f"amqp://{RABBITMQ_HOST}/")

    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=1)

        queue = await channel.declare_queue(
            SUBMIT_QUEUE,
            durable=False,
            arguments={
                'x-dead-letter-exchange': DLX_EXCHANGE,
                'x-dead-letter-routing-key': DLX_SUBMIT_QUEUE,
            }
        )
        logger.info("Worker listening on queue: %s", SUBMIT_QUEUE)
        await queue.consume(submit_callback)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())