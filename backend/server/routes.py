from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List

from .models import SubmitRequest, RunRequest
from .messaging import RabbitMQClient
from .config import SUBMIT_EXCHANGE, SUBMIT_ROUTING_KEY, RUN_EXCHANGE, RUN_ROUTING_KEY

from server.db.database import get_db_session
from server.db.models import Problem, ProblemVersion, Submission, User, TestCase
from server.auth import get_current_user

router = APIRouter()
mq = RabbitMQClient()


import uuid
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
        status="PENDING"
    )
    db.add(new_submission)
    await db.commit()
    await db.refresh(new_submission)
    
    # Fetch TestCases
    stmt_test_cases = select(TestCase).where(TestCase.problem_version_id == latest_version.id)
    result_test_cases = await db.execute(stmt_test_cases)
    test_cases = result_test_cases.scalars().all()

    if not test_cases:
        # Fallback if problem has no specific test cases migrated yet
        test_cases_payload = [{
            "input": "3\n3 2 4\n6\n",
            "expected_output": "1 2\n",
        }]
    else:
        test_cases_payload = [{
            "input": tc.input_data,
            "expected_output": tc.expected_output,
        } for tc in test_cases]

    # 4. Enqueue task for worker
    callback_url = f"http://127.0.0.1:9000/webhook/submit/{new_submission.id}"
    
    payload = {
        "language": submit_request.language,
        "time_limit": latest_version.time_limit_ms,
        "memory_limit": latest_version.memory_limit_mb,
        "src_code": submit_request.src_code,
        "test_cases": test_cases_payload,  # Replaces std_in / expected_out
        "callback_url": callback_url
    }
    
    await mq.publish_message(SUBMIT_EXCHANGE, SUBMIT_ROUTING_KEY, body=payload)
    return {"msg": "submit task enqueued", "submission_id": new_submission.id}

from pydantic import BaseModel
class WebhookPayload(BaseModel):
    status: str

@router.post('/webhook/submit/{submission_id}')
async def webhook_submit(submission_id: int, payload: WebhookPayload, db: AsyncSession = Depends(get_db_session)):
    stmt = select(Submission).where(Submission.id == submission_id)
    result = await db.execute(stmt)
    submission = result.scalars().first()
    
    if submission:
        submission.status = payload.status
        # Mocking time and memory for now
        submission.execution_time_ms = 45.0
        submission.peak_memory_mb = 14.2
        await db.commit()
        
    return {"msg": "ok"}


@router.post('/run')
async def run(run_request: RunRequest):
    await mq.publish_message(RUN_EXCHANGE, RUN_ROUTING_KEY, body=run_request.model_dump())
    return {"msg": "run task enqueued, result will be available at the callback server"}

@router.get('/problems')
async def list_problems(db: AsyncSession = Depends(get_db_session)):
    stmt = select(Problem).where(Problem.is_published == True)
    result = await db.execute(stmt)
    problems = result.scalars().all()
    
    # Map to frontend expected structure
    # In a real app we'd join tags, acceptance rate, etc.
    return [
        {
            "id": p.id,
            "title": p.title,
            "difficulty": "Medium", # Mock data
            "acceptance": 45.2,     # Mock data
            "tags": ["Array", "Algorithm"]
        }
        for p in problems
    ]

@router.get('/problems/{problem_id}')
async def get_problem(problem_id: int, db: AsyncSession = Depends(get_db_session)):
    stmt = select(Problem).where(Problem.id == problem_id)
    result = await db.execute(stmt)
    problem = result.scalars().first()
    
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")
        
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
        
    # Download statement markdown from Blob Storage!
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
        # Fetch problem title (Very inefficient N+1 query here just for quick demo purposes)
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
            "problem_id": sub.problem_version_id, # Simplified
            "problem_title": problem_title,
            "status": sub.status,
            "language": sub.language,
            "time": f"{sub.execution_time_ms}ms" if sub.execution_time_ms else "-",
            "memory": f"{sub.peak_memory_mb}MB" if sub.peak_memory_mb else "-",
            "date": sub.submitted_at.isoformat() if sub.submitted_at else ""
        })
        
    return response
