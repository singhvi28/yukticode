import asyncio
import hashlib
import hmac
import json
import uuid
from datetime import datetime as dt
import datetime

from fastapi import APIRouter, Depends, HTTPException, WebSocket, Request, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from typing import List
import pytz
from pydantic import BaseModel

from .models import SubmitRequest, RunRequest, RunBatchRequest
from .config import SUBMIT_EXCHANGE, SUBMIT_ROUTING_KEY, RUN_EXCHANGE, RUN_ROUTING_KEY, WEBHOOK_SECRET
from .ws import manager as ws_manager
from server.leaderboard import update_leaderboard_on_verdict

from server.db.database import get_db_session
from server.db.models import Problem, Submission, User, TestCase, Contest, ContestProblem
from server.auth import get_current_user
from urllib.parse import quote

router = APIRouter()


# ---------------------------------------------------------------------------
# /submit
# ---------------------------------------------------------------------------

@router.post('/submit')
async def submit(
    submit_request: SubmitRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    # 1. Fetch published problem
    stmt = select(Problem).where(
        Problem.id == submit_request.problem_id,
        Problem.is_published == True,
    )
    result = await db.execute(stmt)
    problem = result.scalars().first()

    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found or is not published")

    # 2. Contest timing enforcement (IDOR fix — don't allow early submissions to contest problems)
    if submit_request.contest_id:
        contest_stmt = (
            select(Contest)
            .join(ContestProblem, Contest.id == ContestProblem.contest_id)
            .where(
                ContestProblem.problem_id == submit_request.problem_id,
                Contest.id == submit_request.contest_id,
            )
        )
        contest_result = await db.execute(contest_stmt)
        contest = contest_result.scalars().first()
        if contest and contest.start_time:
            current_time = dt.now(datetime.timezone.utc)
            start_time = contest.start_time
            if getattr(start_time, "tzinfo", None) is None:
                start_time = start_time.replace(tzinfo=datetime.timezone.utc)
            if current_time < start_time:
                raise HTTPException(
                    status_code=403,
                    detail="This problem is locked until the contest starts.",
                )

    # 3. Create Submission record (source stored in Postgres)
    new_submission = Submission(
        user_id=current_user.id,
        problem_id=problem.id,
        language=submit_request.language,
        code=submit_request.src_code,
        status="PENDING",
        contest_id=submit_request.contest_id if submit_request.contest_id else None,
    )
    db.add(new_submission)
    await db.commit()
    await db.refresh(new_submission)

    # 4. Enqueue task — send only submission_id; worker fetches test cases from DB
    callback_url = f"http://backend:9000/webhook/submit/{new_submission.id}"

    payload = {
        "submission_id": new_submission.id,
        "language": submit_request.language,
        "time_limit": problem.time_limit_ms,
        "memory_limit": problem.memory_limit_mb,
        "callback_url": callback_url,
    }

    mq = request.app.state.mq
    await mq.publish_message(SUBMIT_EXCHANGE, SUBMIT_ROUTING_KEY, body=payload)
    return {"msg": "submit task enqueued", "submission_id": new_submission.id}


# ---------------------------------------------------------------------------
# WebSocket endpoint — clients subscribe here immediately after POST /submit
# ---------------------------------------------------------------------------

@router.websocket("/ws/submissions/{submission_id}")
async def ws_submission_status(submission_id: int, websocket: WebSocket):
    """
    Push-based verdict delivery.

    connect() registers the socket and returns a done_event that is set
    by ws_manager.broadcast() once the final verdict is delivered server-side.
    If the client disconnects early (page refresh / navigation),
    disconnect() sets the event too, so this coroutine never leaks.
    """
    done_event = await ws_manager.connect(submission_id, websocket)
    try:
        # Race-condition fix: verdict may have arrived before we connected.
        cached = await ws_manager.get_cached_result(submission_id)
        if cached:
            await websocket.send_text(json.dumps(cached))
            await websocket.close()
            return

        # Wait until broadcast() or disconnect() sets the event.
        try:
            await done_event.wait()
        except asyncio.CancelledError:
            pass
    finally:
        ws_manager.disconnect(submission_id, websocket)


# ---------------------------------------------------------------------------
# Webhook — called by the worker when judging is complete
# ---------------------------------------------------------------------------



def _verify_webhook_signature(request_body: bytes, signature_header: str) -> bool:
    """
    Verify the HMAC-SHA256 signature sent by the worker.
    Returns True if valid, False otherwise.
    If WEBHOOK_SECRET is not configured, always passes (dev mode).
    """
    if not WEBHOOK_SECRET:
        return True
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), request_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header or "")

@router.post('/webhook/submit/{submission_id}')
async def webhook_submit(
    submission_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    # Verify HMAC signature to prevent unauthenticated verdict injection
    raw_body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")
    if not _verify_webhook_signature(raw_body, sig):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    # Manually parse the JSON after reading the body stream
    payload_dict = json.loads(raw_body)
    status = payload_dict.get("status")
    execution_time_ms = payload_dict.get("execution_time_ms", 0.0)
    peak_memory_mb = payload_dict.get("peak_memory_mb", 0.0)

    stmt = select(Submission).where(Submission.id == submission_id)
    result = await db.execute(stmt)
    submission = result.scalars().first()

    if submission:
        submission.status = status
        submission.execution_time_ms = execution_time_ms
        submission.peak_memory_mb = peak_memory_mb
        await db.commit()

        if ws_manager.redis:
            await update_leaderboard_on_verdict(ws_manager.redis, db, submission_id, status)

        # Push result to any open WebSocket clients
        await ws_manager.broadcast(submission_id, {
            "status": status,
            "execution_time_ms": execution_time_ms,
            "peak_memory_mb": peak_memory_mb,
        })

    return {"msg": "ok"}


# ---------------------------------------------------------------------------
# /run  and  /run_batch
# ---------------------------------------------------------------------------

@router.post('/run')
async def run(run_request: RunRequest, request: Request):
    """
    Enqueue a custom run execution. Generates a unique run_id and pushes the
    payload to RabbitMQ. The worker reports the verdict via gRPC using run_id.
    """
    run_id = str(uuid.uuid4())

    run_payload = run_request.model_dump()
    run_payload['run_id'] = run_id

    mq = request.app.state.mq
    await mq.publish_message(RUN_EXCHANGE, RUN_ROUTING_KEY, body=run_payload)
    return {"msg": "run task enqueued", "run_id": run_id}


@router.post('/run_batch')
async def run_batch(batch_request: RunBatchRequest, request: Request):
    """
    Enqueue a batch of custom test runs as a single RabbitMQ message.
    The worker executes all tests and streams per-test results via gRPC
    using batch_id as the correlation key for WebSocket clients.
    """
    batch_id = str(uuid.uuid4())

    payload = {
        "batch": True,
        "batch_id": batch_id,
        "language": batch_request.language,
        "time_limit": batch_request.time_limit,
        "memory_limit": batch_request.memory_limit,
        "src_code": batch_request.src_code,
        "tests": [t.model_dump() for t in batch_request.tests],
    }

    mq = request.app.state.mq
    await mq.publish_message(RUN_EXCHANGE, RUN_ROUTING_KEY, body=payload)
    return {"msg": "batch run enqueued", "batch_id": batch_id}

@router.post('/webhook/run/{run_id}')
async def webhook_run(run_id: str, payload: dict = Body(...)):
    """
    The run worker hits this endpoint to deliver the result of a custom test case.
    We immediately broadcast the result out to any listening WebSockets.
    """
    await ws_manager.broadcast(run_id, payload)
    return {"msg": "ok"}

@router.websocket("/ws/runs/{run_id}")
async def websocket_run(websocket: WebSocket, run_id: str):
    """
    Clients connect here after calling POST /run or POST /run_batch.

    For batch runs, broadcast() is called with close_after=False for each
    partial test result, and close_after=True on _batch_complete. The
    done_event is only set on that final close, so the socket stays open
    for the full stream without any client-sent messages required.
    """
    done_event = await ws_manager.connect(run_id, websocket)
    try:
        cached = await ws_manager.get_cached_result(run_id)
        if cached:
            await websocket.send_text(json.dumps(cached))
            await websocket.close()
            return

        try:
            await done_event.wait()
        except asyncio.CancelledError:
            pass
    finally:
        ws_manager.disconnect(run_id, websocket)

# ---------------------------------------------------------------------------
# Problems
# ---------------------------------------------------------------------------

@router.get('/problems')
async def list_problems(db: AsyncSession = Depends(get_db_session)):
    stmt = (
        select(
            Problem,
            func.count(Submission.id).filter(Submission.status == 'AC').label('ac_count'),
            func.count(Submission.id).label('total_count')
        )
        .outerjoin(Submission, Submission.problem_id == Problem.id)
        .where(Problem.is_published == True)
        .group_by(Problem.id)
        .order_by(Problem.id)
    )
    result = await db.execute(stmt)
    rows = result.all()

    problems_data = []
    for problem, ac_count, total_count in rows:
        acceptance = (ac_count / total_count * 100) if total_count > 0 else 0.0
        try:
            tags = json.loads(problem.tags) if problem.tags else []
        except Exception:
            tags = []

        problems_data.append({
            "id": problem.id,
            "title": problem.title,
            "difficulty": problem.difficulty or "Medium",
            "acceptance": round(acceptance, 1),
            "tags": tags
        })

    return problems_data

@router.get('/problems/{problem_id}')
async def get_problem(problem_id: int, db: AsyncSession = Depends(get_db_session)):
    stmt = select(Problem).where(Problem.id == problem_id)
    result = await db.execute(stmt)
    problem = result.scalars().first()

    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")

    # Contest freeze: if problem is part of a contest that hasn't started, block access
    contest_stmt = (
        select(Contest)
        .join(ContestProblem, Contest.id == ContestProblem.contest_id)
        .where(ContestProblem.problem_id == problem_id)
    )
    contest_result = await db.execute(contest_stmt)
    linked_contests = contest_result.scalars().all()
    current_time = dt.now(datetime.timezone.utc)
    for contest in linked_contests:
        if contest.start_time:
            start_time = contest.start_time
            if getattr(start_time, "tzinfo", None) is None:
                start_time = start_time.replace(tzinfo=datetime.timezone.utc)
            if current_time < start_time:
                raise HTTPException(
                    status_code=403,
                    detail="This problem is locked until the contest starts.",
                )

    statement_markdown = problem.statement or "No statement available."

    # Sample cases from DB (is_sample=True)
    sample_stmt = (
        select(TestCase)
        .where(
            TestCase.problem_id == problem.id,
            TestCase.is_sample == True,
        )
        .order_by(TestCase.id)
    )
    sample_result = await db.execute(sample_stmt)
    sample_rows = sample_result.scalars().all()
    samples = [
        {"id": tc.id, "input": tc.input_data, "output": tc.expected_output}
        for tc in sample_rows
    ]

    return {
        "id": problem.id,
        "title": problem.title,
        "timeLimit": problem.time_limit_ms,
        "memoryLimit": problem.memory_limit_mb,
        "statement": statement_markdown,
        "samples": samples,
    }

# ---------------------------------------------------------------------------
# Submissions
# ---------------------------------------------------------------------------

@router.get('/submissions/{submission_id}')
async def get_submission(submission_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    stmt = select(Submission).where(Submission.id == submission_id, Submission.user_id == current_user.id)
    result = await db.execute(stmt)
    submission = result.scalars().first()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    return {
        "id": submission.id,
        "status": submission.status,
        "execution_time_ms": submission.execution_time_ms,
        "peak_memory_mb": submission.peak_memory_mb
    }

@router.get('/submissions')
async def list_submissions(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    stmt = (
        select(Submission)
        .options(joinedload(Submission.problem))
        .where(Submission.user_id == current_user.id)
        .order_by(Submission.submitted_at.desc())
    )
    result = await db.execute(stmt)
    submissions = result.unique().scalars().all()

    response = []
    for sub in submissions:
        problem_title = sub.problem.title if sub.problem else "Unknown"

        response.append({
            "id": sub.id,
            "problem_id": sub.problem_id,
            "problem_title": problem_title,
            "status": sub.status,
            "language": sub.language,
            "time": f"{sub.execution_time_ms:.1f}ms" if sub.execution_time_ms else "-",
            "memory": f"{sub.peak_memory_mb:.1f}MB" if sub.peak_memory_mb else "-",
            "date": sub.submitted_at.isoformat() if sub.submitted_at else ""
        })

    return response
