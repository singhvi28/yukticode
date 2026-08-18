"""
Admin API Router — /admin/*

All endpoints require is_admin=True on the authenticated user.
Covers:
  - Problem CRUD (incl. publish toggle, statement stored in Postgres)
  - TestCase CRUD + dry-run judging via the existing /run endpoint
  - Contest CRUD + problem assignment
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel, Field
from typing import Optional, List
import uuid

from server.db.database import get_db_session
from server.db.models import User, Problem, TestCase, Contest, ContestProblem, Submission
from server.auth import get_current_user
from server.config import RUN_EXCHANGE, RUN_ROUTING_KEY, REDIS_URL
from server.ws import manager as ws_manager

import datetime
import json
import redis.asyncio as aioredis

router = APIRouter(prefix="/admin", tags=["admin"])

# Redis client for storing dry-run expected outputs (multi-process safe)
_redis = None
async def _get_redis():
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

async def admin_required(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ProblemCreate(BaseModel):
    title: str
    statement: str = ""
    time_limit_ms: int = 2000
    memory_limit_mb: int = 256

class ProblemUpdate(BaseModel):
    title: Optional[str] = None
    statement: Optional[str] = None
    time_limit_ms: Optional[int] = None
    memory_limit_mb: Optional[int] = None
    is_published: Optional[bool] = None

class TestCaseCreate(BaseModel):
    input_data: str
    expected_output: str
    is_sample: bool = False
    score: int = Field(default=10, ge=0)

class TestCaseUpdate(BaseModel):
    input_data: Optional[str] = None
    expected_output: Optional[str] = None
    is_sample: Optional[bool] = None
    score: Optional[int] = Field(default=None, ge=0)

class TestCaseRunRequest(BaseModel):
    language: str = "py"
    src_code: str

class ContestCreate(BaseModel):
    title: str
    description: str = ""
    start_time: Optional[datetime.datetime] = None
    end_time: Optional[datetime.datetime] = None

class ContestUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[datetime.datetime] = None
    end_time: Optional[datetime.datetime] = None
    is_published: Optional[bool] = None

class ContestProblemAdd(BaseModel):
    problem_id: int
    score: int = 100
    display_order: int = 0


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _get_problem(problem_id: int, db: AsyncSession) -> Problem:
    result = await db.execute(select(Problem).where(Problem.id == problem_id))
    problem = result.scalars().first()
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")
    return problem


# ---------------------------------------------------------------------------
# Problem endpoints
# ---------------------------------------------------------------------------

@router.get("/problems")
async def admin_list_problems(
    admin: User = Depends(admin_required),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(Problem).order_by(Problem.id))
    problems = result.scalars().all()
    return [
        {
            "id": p.id,
            "title": p.title,
            "is_published": p.is_published,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in problems
    ]


@router.post("/problems", status_code=201)
async def admin_create_problem(
    payload: ProblemCreate,
    admin: User = Depends(admin_required),
    db: AsyncSession = Depends(get_db_session),
):
    # Check title uniqueness
    existing = await db.execute(select(Problem).where(Problem.title == payload.title))
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="A problem with this title already exists")

    problem = Problem(
        title=payload.title,
        author_id=admin.id,
        is_published=False,
        statement=payload.statement or "",
        time_limit_ms=payload.time_limit_ms,
        memory_limit_mb=payload.memory_limit_mb,
    )
    db.add(problem)
    await db.commit()
    await db.refresh(problem)

    return {"id": problem.id, "title": problem.title, "is_published": problem.is_published}


@router.patch("/problems/{problem_id}")
async def admin_update_problem(
    problem_id: int,
    payload: ProblemUpdate,
    admin: User = Depends(admin_required),
    db: AsyncSession = Depends(get_db_session),
):
    problem = await _get_problem(problem_id, db)

    if payload.title is not None:
        problem.title = payload.title
    if payload.is_published is not None:
        problem.is_published = payload.is_published
    if payload.statement is not None:
        problem.statement = payload.statement
    if payload.time_limit_ms is not None:
        problem.time_limit_ms = payload.time_limit_ms
    if payload.memory_limit_mb is not None:
        problem.memory_limit_mb = payload.memory_limit_mb

    await db.commit()
    return {"msg": "updated", "id": problem.id}


@router.delete("/problems/{problem_id}", status_code=204)
async def admin_delete_problem(
    problem_id: int,
    admin: User = Depends(admin_required),
    db: AsyncSession = Depends(get_db_session),
):
    problem = await _get_problem(problem_id, db)

    await db.execute(
        Submission.__table__.delete().where(Submission.problem_id == problem_id)
    )
    await db.execute(
        ContestProblem.__table__.delete().where(ContestProblem.problem_id == problem_id)
    )

    await db.delete(problem)
    await db.commit()


# ---------------------------------------------------------------------------
# Test case endpoints
# ---------------------------------------------------------------------------

@router.get("/problems/{problem_id}/testcases")
async def admin_list_testcases(
    problem_id: int,
    admin: User = Depends(admin_required),
    db: AsyncSession = Depends(get_db_session),
):
    await _get_problem(problem_id, db)
    result = await db.execute(
        select(TestCase).where(TestCase.problem_id == problem_id).order_by(TestCase.id)
    )
    tcs = result.scalars().all()
    return [
        {
            "id": tc.id,
            "input_data": tc.input_data,
            "expected_output": tc.expected_output,
            "is_sample": tc.is_sample,
            "score": tc.score,
        }
        for tc in tcs
    ]


@router.post("/problems/{problem_id}/testcases", status_code=201)
async def admin_create_testcase(
    problem_id: int,
    payload: TestCaseCreate,
    admin: User = Depends(admin_required),
    db: AsyncSession = Depends(get_db_session),
):
    await _get_problem(problem_id, db)
    tc = TestCase(
        problem_id=problem_id,
        input_data=payload.input_data,
        expected_output=payload.expected_output,
        is_sample=payload.is_sample,
        score=payload.score,
    )
    db.add(tc)
    await db.commit()
    await db.refresh(tc)
    return {"id": tc.id, "msg": "created"}


@router.put("/problems/{problem_id}/testcases/{tc_id}")
async def admin_update_testcase(
    problem_id: int,
    tc_id: int,
    payload: TestCaseUpdate,
    admin: User = Depends(admin_required),
    db: AsyncSession = Depends(get_db_session),
):
    await _get_problem(problem_id, db)
    result = await db.execute(
        select(TestCase).where(TestCase.id == tc_id, TestCase.problem_id == problem_id)
    )
    tc = result.scalars().first()
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")

    if payload.input_data is not None:
        tc.input_data = payload.input_data
    if payload.expected_output is not None:
        tc.expected_output = payload.expected_output
    if payload.is_sample is not None:
        tc.is_sample = payload.is_sample
    if payload.score is not None:
        tc.score = payload.score

    await db.commit()
    return {"msg": "updated", "id": tc.id}


@router.delete("/problems/{problem_id}/testcases/{tc_id}", status_code=204)
async def admin_delete_testcase(
    problem_id: int,
    tc_id: int,
    admin: User = Depends(admin_required),
    db: AsyncSession = Depends(get_db_session),
):
    await _get_problem(problem_id, db)
    result = await db.execute(
        select(TestCase).where(TestCase.id == tc_id, TestCase.problem_id == problem_id)
    )
    tc = result.scalars().first()
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")
    await db.delete(tc)
    await db.commit()


@router.post("/problems/{problem_id}/testcases/{tc_id}/run")
async def admin_run_testcase(
    problem_id: int,
    tc_id: int,
    payload: TestCaseRunRequest,
    request: Request,
    admin: User = Depends(admin_required),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Dry-run: enqueue src_code against a specific test case via RabbitMQ.
    Stores expected output in Redis keyed by run_id; the webhook /webhook/run
    handler compares and broadcasts the final AC/WA verdict.
    """
    problem = await _get_problem(problem_id, db)
    result = await db.execute(
        select(TestCase).where(TestCase.id == tc_id, TestCase.problem_id == problem_id)
    )
    tc = result.scalars().first()
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")

    run_id = str(uuid.uuid4())

    # Store expected_output before enqueue so the webhook can compare
    # even if the worker finishes very quickly.
    r = await _get_redis()
    await r.set(f"admin_run:{run_id}", json.dumps({
        "expected_output": tc.expected_output,
    }), ex=60)

    run_payload = {
        "run_id": run_id,
        "language": payload.language,
        "time_limit": problem.time_limit_ms,
        "memory_limit": problem.memory_limit_mb,
        "src_code": payload.src_code,
        "std_in": tc.input_data,
    }

    mq = request.app.state.mq
    await mq.publish_message(RUN_EXCHANGE, RUN_ROUTING_KEY, body=run_payload)

    return {"run_id": run_id, "msg": "Run enqueued. Connect to WS /ws/runs/{run_id} for result."}


# ---------------------------------------------------------------------------
# Dry-run polling fallback
# ---------------------------------------------------------------------------

@router.get("/run-result/{run_id}")
async def admin_poll_run_result(run_id: str, admin: User = Depends(admin_required)):
    """Poll for the result of a dry-run test case (fallback if WebSocket fails)."""
    r = await _get_redis()
    raw = await r.get(f"admin_result:{run_id}")
    if raw:
        await r.delete(f"admin_result:{run_id}")
        return json.loads(raw)

    # Still pending?
    pending = await r.get(f"admin_run:{run_id}")
    if pending:
        return {"status": "pending"}

    raise HTTPException(status_code=404, detail="Run ID not found or expired")


# ---------------------------------------------------------------------------
# Contest endpoints
# ---------------------------------------------------------------------------

@router.get("/contests")
async def admin_list_contests(
    admin: User = Depends(admin_required),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(Contest).order_by(Contest.id))
    contests = result.scalars().all()
    return [
        {
            "id": c.id,
            "title": c.title,
            "description": c.description,
            "start_time": c.start_time.isoformat() if c.start_time else None,
            "end_time": c.end_time.isoformat() if c.end_time else None,
            "is_published": c.is_published,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in contests
    ]


@router.post("/contests", status_code=201)
async def admin_create_contest(
    payload: ContestCreate,
    admin: User = Depends(admin_required),
    db: AsyncSession = Depends(get_db_session),
):
    existing = await db.execute(select(Contest).where(Contest.title == payload.title))
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Contest with this title already exists")

    contest = Contest(
        title=payload.title,
        description=payload.description,
        start_time=payload.start_time,
        end_time=payload.end_time,
        created_by=admin.id,
    )
    db.add(contest)
    await db.commit()
    await db.refresh(contest)
    return {"id": contest.id, "title": contest.title}


@router.get("/contests/{contest_id}")
async def admin_get_contest(
    contest_id: int,
    admin: User = Depends(admin_required),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(Contest).where(Contest.id == contest_id))
    contest = result.scalars().first()
    if not contest:
        raise HTTPException(status_code=404, detail="Contest not found")

    # Fetch associated problems
    cp_result = await db.execute(
        select(ContestProblem).where(ContestProblem.contest_id == contest_id).order_by(ContestProblem.display_order)
    )
    cps = cp_result.scalars().all()
    problems = []
    for cp in cps:
        p_result = await db.execute(select(Problem).where(Problem.id == cp.problem_id))
        p = p_result.scalars().first()
        if p:
            problems.append({"id": p.id, "title": p.title, "score": cp.score, "display_order": cp.display_order, "cp_id": cp.id})

    return {
        "id": contest.id,
        "title": contest.title,
        "description": contest.description,
        "start_time": contest.start_time.isoformat() if contest.start_time else None,
        "end_time": contest.end_time.isoformat() if contest.end_time else None,
        "is_published": contest.is_published,
        "problems": problems,
    }


@router.patch("/contests/{contest_id}")
async def admin_update_contest(
    contest_id: int,
    payload: ContestUpdate,
    admin: User = Depends(admin_required),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(Contest).where(Contest.id == contest_id))
    contest = result.scalars().first()
    if not contest:
        raise HTTPException(status_code=404, detail="Contest not found")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(contest, field, value)

    await db.commit()
    return {"msg": "updated", "id": contest.id}


@router.delete("/contests/{contest_id}", status_code=204)
async def admin_delete_contest(
    contest_id: int,
    admin: User = Depends(admin_required),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(Contest).where(Contest.id == contest_id))
    contest = result.scalars().first()
    if not contest:
        raise HTTPException(status_code=404, detail="Contest not found")
    await db.delete(contest)
    await db.commit()


@router.post("/contests/{contest_id}/problems", status_code=201)
async def admin_add_contest_problem(
    contest_id: int,
    payload: ContestProblemAdd,
    admin: User = Depends(admin_required),
    db: AsyncSession = Depends(get_db_session),
):
    # Ensure contest exists
    c_result = await db.execute(select(Contest).where(Contest.id == contest_id))
    if not c_result.scalars().first():
        raise HTTPException(status_code=404, detail="Contest not found")

    # Ensure problem exists
    p_result = await db.execute(select(Problem).where(Problem.id == payload.problem_id))
    if not p_result.scalars().first():
        raise HTTPException(status_code=404, detail="Problem not found")

    cp = ContestProblem(
        contest_id=contest_id,
        problem_id=payload.problem_id,
        score=payload.score,
        display_order=payload.display_order,
    )
    db.add(cp)
    try:
        await db.commit()
    except Exception:
        raise HTTPException(status_code=409, detail="Problem already added to this contest")

    return {"msg": "problem added to contest"}


@router.delete("/contests/{contest_id}/problems/{problem_id}", status_code=204)
async def admin_remove_contest_problem(
    contest_id: int,
    problem_id: int,
    admin: User = Depends(admin_required),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(ContestProblem).where(
            ContestProblem.contest_id == contest_id,
            ContestProblem.problem_id == problem_id,
        )
    )
    cp = result.scalars().first()
    if not cp:
        raise HTTPException(status_code=404, detail="Association not found")
    await db.delete(cp)
    await db.commit()
