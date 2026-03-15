from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Request, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from typing import List
import json

from .models import SubmitRequest, RunRequest, RunBatchRequest
from .messaging import RabbitMQClient
from .config import SUBMIT_EXCHANGE, SUBMIT_ROUTING_KEY, RUN_EXCHANGE, RUN_ROUTING_KEY
from .ws import manager as ws_manager
from server.leaderboard import update_leaderboard_on_verdict

from server.db.database import get_db_session
from server.db.models import Problem, ProblemVersion, Submission, User, TestCase, Contest, ContestProblem
from server.auth import get_current_user

router = APIRouter()
mq = RabbitMQClient()


import uuid
from datetime import datetime as dt
import pytz
from pydantic import BaseModel
from server.blob_storage import upload_text, download_text
from urllib.parse import quote

@router.post('/submit')
async def submit(submit_request: SubmitRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    # 1. Fetch Problem Version
    stmt_version = select(ProblemVersion).where(ProblemVersion.problem_id == submit_request.problem_id).order_by(ProblemVersion.version_number.desc())
    result_version = await db.execute(stmt_version)
    latest_version = result_version.scalars().first()
    
    if not latest_version:
        raise HTTPException(status_code=404, detail="Problem version not found")

    # 2. Upload code to Blob Storage
    object_name = f"{uuid.uuid4()}.{submit_request.language}"
    code_url = upload_text("submissions", object_name, submit_request.src_code)
    
    # 3. Create Submission record
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
    
    # Fetch TestCases
    stmt_test_cases = select(TestCase).where(TestCase.problem_version_id == latest_version.id)
    result_test_cases = await db.execute(stmt_test_cases)
    test_cases = result_test_cases.scalars().all()

    if not test_cases:
        raise HTTPException(status_code=400, detail="Problem misconfigured: No test cases found")

    test_cases_payload = [{
        "input": tc.input_data,
        "expected_output": tc.expected_output,
    } for tc in test_cases]

    # 4. Enqueue task for worker
    # Hardcoded internal URL bypasses Nginx to prevent path stripping issues
    callback_url = f"http://backend:9000/webhook/submit/{new_submission.id}"
    
    payload = {
        "language": submit_request.language,
        "time_limit": latest_version.time_limit_ms,
        "memory_limit": latest_version.memory_limit_mb,
        "src_code": submit_request.src_code,
        "test_cases": test_cases_payload,
        "callback_url": callback_url
    }
    
    await mq.publish_message(SUBMIT_EXCHANGE, SUBMIT_ROUTING_KEY, body=payload)
    return {"msg": "submit task enqueued", "submission_id": new_submission.id}


# ---------------------------------------------------------------------------
# WebSocket endpoint — clients subscribe here immediately after POST /submit
# ---------------------------------------------------------------------------

@router.websocket("/ws/submissions/{submission_id}")
async def ws_submission_status(submission_id: int, websocket: WebSocket):
    """
    Push-based alternative to polling /submissions/{id}.
    After connecting, we first check Redis for a cached result (race-condition
    fix). If the worker already finished, the client gets the result
    immediately and the socket closes.
    """
    await ws_manager.connect(submission_id, websocket)
    try:
        # Check if the result is already cached (worker beat us)
        cached = await ws_manager.get_cached_result(submission_id)
        if cached:
            import json
            await websocket.send_text(json.dumps(cached))
            await websocket.close()
            return

        # Otherwise wait for the broadcast
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(submission_id, websocket)


# ---------------------------------------------------------------------------
# Webhook — called by the worker when judging is complete
# ---------------------------------------------------------------------------

class WebhookPayload(BaseModel):
    status: str
    execution_time_ms: float = 0.0
    peak_memory_mb: float = 0.0

@router.post('/webhook/submit/{submission_id}')
async def webhook_submit(submission_id: int, payload: WebhookPayload, db: AsyncSession = Depends(get_db_session)):
    stmt = select(Submission).where(Submission.id == submission_id)
    result = await db.execute(stmt)
    submission = result.scalars().first()
    
    if submission:
        submission.status = payload.status
        submission.execution_time_ms = payload.execution_time_ms
        submission.peak_memory_mb = payload.peak_memory_mb
        await db.commit()

        if ws_manager.redis:
            await update_leaderboard_on_verdict(ws_manager.redis, db, submission_id, payload.status)

        # Push result to any open WebSocket clients
        await ws_manager.broadcast(submission_id, {
            "status": payload.status,
            "execution_time_ms": payload.execution_time_ms,
            "peak_memory_mb": payload.peak_memory_mb,
        })
        
    return {"msg": "ok"}


@router.post('/run')
async def run(run_request: RunRequest, request: Request):
    """
    Enqueue a custom run execution. Generates a unique run_id, attaches the webhook
    callback URL, and pushes the payload to RabbitMQ.
    """
    run_id = str(uuid.uuid4())
    
    # Construct the absolute internal callback URL for the worker to hit
    # Hardcoded internal URL bypasses Nginx to prevent path stripping issues
    callback_url = f"http://backend:9000/webhook/run/{run_id}"
        
    run_payload = run_request.model_dump()
    run_payload['callback_url'] = callback_url
    
    await mq.publish_message(RUN_EXCHANGE, RUN_ROUTING_KEY, body=run_payload)
    return {"msg": "run task enqueued", "run_id": run_id}


@router.post('/run_batch')
async def run_batch(batch_request: RunBatchRequest, request: Request):
    """
    Enqueue a batch of custom test runs as a single RabbitMQ message.
    The worker will execute all tests sequentially inside one container and
    POST a single webhook containing per-test results.
    """
    batch_id = str(uuid.uuid4())

    # Hardcoded internal URL bypasses Nginx to prevent path stripping issues
    callback_url = f"http://backend:9000/webhook/run/{batch_id}"

    payload = {
        "batch": True,
        "language": batch_request.language,
        "time_limit": batch_request.time_limit,
        "memory_limit": batch_request.memory_limit,
        "src_code": batch_request.src_code,
        "tests": [t.model_dump() for t in batch_request.tests],
        "callback_url": callback_url,
    }

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
    Clients connect here after calling POST /run to receive real-time execution results.
    Checks Redis cache first in case the worker already finished.
    """
    await ws_manager.connect(run_id, websocket)
    try:
        # Check if the result is already cached (worker beat us)
        cached = await ws_manager.get_cached_result(run_id)
        if cached:
            import json
            await websocket.send_text(json.dumps(cached))
            await websocket.close()
            return

        # Otherwise wait for the broadcast
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(run_id, websocket)
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
        except:
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
    current_time = dt.now(pytz.utc)
    for contest in linked_contests:
        if contest.start_time:
            start_time = contest.start_time
            if getattr(start_time, "tzinfo", None) is None:
                start_time = pytz.utc.localize(start_time)
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
    stmt = select(Submission).where(Submission.user_id == current_user.id).order_by(Submission.submitted_at.desc())
    result = await db.execute(stmt)
    submissions = result.scalars().all()
    
    response = []
    for sub in submissions:
        problem_title = "Unknown"
        if sub.problem_version_id:
            pv_stmt = select(ProblemVersion).where(ProblemVersion.id == sub.problem_version_id)
            pv_res = await db.execute(pv_stmt)
            pv = pv_res.scalars().first()
            if pv:
                p_stmt = select(Problem).where(Problem.id == pv.problem_id)
                p_res = await db.execute(p_stmt)
                p = p_res.scalars().first()
                if p:
                    problem_title = p.title
                    
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
