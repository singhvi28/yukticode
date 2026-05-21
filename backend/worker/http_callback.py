"""
Synchronous HTTP helpers for workers to report verdicts to the FastAPI backend.
"""
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

logger = logging.getLogger(__name__)

INTERNAL_API_URL = os.getenv("INTERNAL_API_URL", "http://backend:9000").rstrip("/")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")


def _signed_headers(body: bytes) -> dict:
    headers = {"Content-Type": "application/json"}
    if WEBHOOK_SECRET:
        sig = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
        headers["X-Hub-Signature-256"] = f"sha256={sig}"
    return headers


def _post_json(url: str, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(url, content=body, headers=_signed_headers(body))
        resp.raise_for_status()


def report_submit_verdict(
    submission_id: int,
    status: str,
    time_ms: float,
    mem_mb: float,
    callback_url: str | None = None,
):
    """Report the final verdict for a /submit judging job."""
    url = callback_url or f"{INTERNAL_API_URL}/webhook/submit/{submission_id}"
    _post_json(url, {
        "status": status,
        "execution_time_ms": time_ms,
        "peak_memory_mb": mem_mb,
    })


def report_run_verdict(
    run_id: str,
    status: str,
    std_out: str,
    time_ms: float,
    mem_mb: float,
    test_index: int = 0,
):
    """Report the result of a single /run execution."""
    url = f"{INTERNAL_API_URL}/webhook/run/{run_id}"
    _post_json(url, {
        "status": status,
        "std_out": std_out,
        "execution_time_ms": time_ms,
        "peak_memory_mb": mem_mb,
        "test_index": test_index,
    })


def stream_batch_verdicts(batch_id: str, results_iterator):
    """
    POST per-test results for a /run_batch job, then a final completion message.
    results_iterator must yield dicts with keys:
        test_index, status, std_out, time_ms, mem_mb
    """
    url = f"{INTERNAL_API_URL}/webhook/run/{batch_id}"
    count = 0
    for res in results_iterator:
        count += 1
        _post_json(url, {
            "test_index": res["test_index"],
            "status": res["status"],
            "std_out": res.get("std_out", ""),
            "execution_time_ms": res["time_ms"],
            "peak_memory_mb": res["mem_mb"],
            "_close_after": False,
        })
    _post_json(url, {"_batch_complete": True, "count": count})
