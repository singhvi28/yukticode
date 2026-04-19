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
from server.db.models import Problem, ProblemVersion, Submission, User, TestCase, Contest, ContestProblem
from server.auth import get_current_user
from server.blob_storage import upload_text, download_text
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
    # 1. Fetch ProblemVersion — JOIN Problem to verify is_published (IDOR fix)
    stmt_version = (
        select(ProblemVersion, Problem)
        .join(Problem, Problem.id == ProblemVersion.problem_id)
        .where(
            ProblemVersion.problem_id == submit_request.problem_id,
            Problem.is_published == True,
        )
        .order_by(ProblemVersion.version_number.desc())
    )
    result_version = await db.execute(stmt_version)
    row = result_version.first()

    if not row:
        raise HTTPException(status_code=404, detail="Problem not found or is not published")

    latest_version, problem = row

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

    # 3. Upload code to Blob Storage
    object_name = f"{uuid.uuid4()}.{submit_request.language}"
    code_url = upload_text("submissions", object_name, submit_request.src_code)

    # 4. Create Submission record
    new_submission = Submission(
        user_id=current_user.id,
        problem_version_id=latest_version.id,
        language=submit_request.language,
        code_url=code_url,
        status="PENDING",
        contest_id=submit_request.contest_id if submit_request.contest_id else None,
    )
    db.add(new_submission)
    await db.commit()
    await db.refresh(new_submission)

    # 5. Enqueue task — send only submission_id; worker fetches test cases from DB
    # (MQ Message Bloat fix: no src_code or test_cases in the payload)
    callback_url = f"http://backend:9000/webhook/submit/{new_submission.id}"

    payload = {
        "submission_id": new_submission.id,
        "language": submit_request.language,
        "time_limit": latest_version.time_limit_ms,
        "memory_limit": latest_version.memory_limit_mb,
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
        .outerjoin(ProblemVersion, ProblemVersion.problem_id == Problem.id)
        .outerjoin(Submission, Submission.problem_version_id == ProblemVersion.id)
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

    # Get latest version
    stmt_version = select(ProblemVersion).where(ProblemVersion.problem_id == problem_id).order_by(ProblemVersion.version_number.desc())
    result_version = await db.execute(stmt_version)
    latest_version = result_version.scalars().first()

    if not latest_version:
        return {
            "id": problem.id,
            "title": problem.title,
            "timeLimit": 2000,
            "memoryLimit": 256,
            "statement": "No statement available.",
            "samples": []
        }

    # Download statement markdown from Blob Storage
    statement_markdown = download_text("problems", latest_version.statement_url)
    if not statement_markdown:
        statement_markdown = "Failed to load statement from Blob Storage."

    return {
        "id": problem.id,
        "title": problem.title,
        "timeLimit": latest_version.time_limit_ms,
        "memoryLimit": latest_version.memory_limit_mb,
        "statement": statement_markdown,
        "samples": [
            {"id": 1, "input": "4\n2 7 11 15\n9", "output": "0 1"},
            {"id": 2, "input": "3\n3 2 4\n6", "output": "1 2"}
        ]
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
    # N+1 fix: single JOIN query fetches Submission + ProblemVersion + Problem together
    stmt = (
        select(Submission)
        .options(
            joinedload(Submission.problem_version).joinedload(ProblemVersion.problem)
        )
        .where(Submission.user_id == current_user.id)
        .order_by(Submission.submitted_at.desc())
    )
    result = await db.execute(stmt)
    # unique() needed when using joinedload to avoid duplicate rows from the JOIN
    submissions = result.unique().scalars().all()

    response = []
    for sub in submissions:
        pv = sub.problem_version
        problem_title = pv.problem.title if pv and pv.problem else "Unknown"

        response.append({
            "id": sub.id,
            "problem_id": sub.problem_version_id,
            "problem_title": problem_title,
            "status": sub.status,
            "language": sub.language,
            "time": f"{sub.execution_time_ms:.1f}ms" if sub.execution_time_ms else "-",
            "memory": f"{sub.peak_memory_mb:.1f}MB" if sub.peak_memory_mb else "-",
            "date": sub.submitted_at.isoformat() if sub.submitted_at else ""
        })

    return response
