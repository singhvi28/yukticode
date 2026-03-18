"""
Synchronous gRPC client helpers for workers to report verdicts directly to
the FastAPI backend's JudgeCoordinator service — no HTTP webhooks required.

Each function opens a short-lived channel, makes one call, then closes it.
This is intentional: workers are long-running processes and keeping a
persistent channel risks silent disconnects. For high-throughput scenarios,
replace with a shared channel + retry interceptor.
"""
import os
import grpc
import judger_pb2
import judger_pb2_grpc

GRPC_TARGET = os.getenv("GRPC_BACKEND", "backend:50051")


def report_submit_verdict(
    submission_id: int,
    status: str,
    time_ms: float,
    mem_mb: float,
):
    """Report the final verdict for a /submit judging job."""
    with grpc.insecure_channel(GRPC_TARGET) as channel:
        stub = judger_pb2_grpc.JudgeCoordinatorStub(channel)
        req = judger_pb2.SubmitVerdictRequest(
            submission_id=str(submission_id),
            status=status,
            execution_time_ms=time_ms,
            peak_memory_mb=mem_mb,
        )
        stub.ReportSubmitVerdict(req)


def report_run_verdict(
    run_id: str,
    status: str,
    std_out: str,
    time_ms: float,
    mem_mb: float,
    test_index: int = 0,
):
    """Report the result of a single /run execution."""
    with grpc.insecure_channel(GRPC_TARGET) as channel:
        stub = judger_pb2_grpc.JudgeCoordinatorStub(channel)
        req = judger_pb2.RunVerdictRequest(
            run_id=run_id,
            status=status,
            std_out=std_out,
            execution_time_ms=time_ms,
            peak_memory_mb=mem_mb,
            test_index=test_index,
        )
        stub.ReportRunVerdict(req)


def stream_batch_verdicts(batch_id: str, results_iterator):
    """
    Stream per-test results for a /run_batch job using the server-side
    streaming gRPC call. results_iterator must yield dicts with keys:
        test_index, status, std_out, time_ms, mem_mb
    """
    def _request_generator():
        for res in results_iterator:
            yield judger_pb2.RunVerdictRequest(
                run_id=batch_id,
                test_index=res["test_index"],
                status=res["status"],
                std_out=res.get("std_out", ""),
                execution_time_ms=res["time_ms"],
                peak_memory_mb=res["mem_mb"],
            )

    with grpc.insecure_channel(GRPC_TARGET) as channel:
        stub = judger_pb2_grpc.JudgeCoordinatorStub(channel)
        stub.StreamBatchRunVerdict(_request_generator())
