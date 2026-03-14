"""
gRPC Judge Coordinator service.

Receives verdicts from workers over gRPC and broadcasts them to WebSocket clients.
Eliminates HTTP callback overhead and enables streaming batch results.
"""
import logging
import sys
import os

# Ensure backend root is on path so judger_pb2 is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import grpc
import judger_pb2
import judger_pb2_grpc
from sqlalchemy.future import select

from .ws import manager as ws_manager
from .db.database import async_session_maker
from server.db.models import Submission

logger = logging.getLogger(__name__)


class JudgeCoordinatorServicer(judger_pb2_grpc.JudgeCoordinatorServicer):
    """Implements the JudgeCoordinator gRPC service."""

    async def ReportSubmitVerdict(self, request, context):
        """Handles standard POST /submit callbacks from submit_worker."""
        try:
            async with async_session_maker() as session:
                stmt = select(Submission).where(Submission.id == int(request.submission_id))
                result = await session.execute(stmt)
                submission = result.scalars().first()
                if submission:
                    submission.status = request.status
                    submission.execution_time_ms = request.execution_time_ms
                    submission.peak_memory_mb = request.peak_memory_mb
                    await session.commit()
        except Exception as e:
            logger.exception("Failed to update submission %s: %s", request.submission_id, e)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return judger_pb2.ReportResponse(success=False, message=str(e))

        await ws_manager.broadcast(request.submission_id, {
            "status": request.status,
            "execution_time_ms": request.execution_time_ms,
            "peak_memory_mb": request.peak_memory_mb,
        })
        return judger_pb2.ReportResponse(success=True, message="OK")

    async def ReportRunVerdict(self, request, context):
        """Handles single custom run (POST /run) callbacks."""
        await ws_manager.broadcast(request.run_id, {
            "test_index": 0,
            "status": request.status,
            "std_out": request.std_out,
            "execution_time_ms": request.execution_time_ms,
            "peak_memory_mb": request.peak_memory_mb,
        })
        return judger_pb2.ReportResponse(success=True, message="OK")

    async def StreamBatchRunVerdict(self, request_iterator, context):
        """Handles live-streaming batch results from custom run worker."""
        batch_id = None
        count = 0

        async for result in request_iterator:
            batch_id = result.run_id
            count += 1
            logger.info("Received partial batch result for %s, test %d", batch_id, result.test_index)

            await ws_manager.broadcast(batch_id, {
                "test_index": result.test_index,
                "status": result.status,
                "std_out": result.std_out,
                "execution_time_ms": result.execution_time_ms,
                "peak_memory_mb": result.peak_memory_mb,
            }, close_after=False)

        if batch_id:
            # Final message so clients know the stream is complete and can close
            await ws_manager.broadcast(batch_id, {"_batch_complete": True, "count": count}, close_after=True)

        return judger_pb2.ReportResponse(success=True, message="Batch fully processed")


async def start_grpc_server(port: int = 50051):
    """Bootstraps the async gRPC server."""
    server = grpc.aio.server()
    judger_pb2_grpc.add_JudgeCoordinatorServicer_to_server(JudgeCoordinatorServicer(), server)
    listen_addr = f"[::]:{port}"
    server.add_insecure_port(listen_addr)
    logger.info("Starting gRPC server on %s", listen_addr)
    await server.start()
    return server
