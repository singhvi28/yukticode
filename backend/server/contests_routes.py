"""
Public contest API — GET /contests, GET /contests/:id, POST /contests/:id/register, GET /contests/:id/leaderboard, SSE stream
"""
import asyncio
import json
from datetime import datetime

import pytz
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from server.auth import get_current_user, get_current_user_optional
from server.db.database import get_db_session
from server.db.models import Contest, ContestProblem, ContestRegistration, Problem, Submission, User
from server.db.models import ProblemVersion
from server.leaderboard import ContestLeaderboardManager
from server.ws import manager as ws_manager

router = APIRouter(prefix="/contests", tags=["contests"])


@router.get("")
async def list_public_contests(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    stmt = select(Contest).where(Contest.is_published == True).order_by(Contest.start_time.desc())
    result = await db.execute(stmt)
    contests = result.scalars().all()

    reg_stmt = select(ContestRegistration.contest_id).where(ContestRegistration.user_id == current_user.id)
    reg_result = await db.execute(reg_stmt)
    registered_contest_ids = {row[0] for row in reg_result.all()}

    response = []
    for c in contests:
        response.append({
            "id": c.id,
            "title": c.title,
            "description": c.description or "",
            "start_time": c.start_time.isoformat() if c.start_time else None,
            "end_time": c.end_time.isoformat() if c.end_time else None,
            "is_registered": c.id in registered_contest_ids,
        })
    return response


@router.get("/{contest_id}")
async def get_public_contest(
    contest_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User | None = Depends(get_current_user_optional),
):
    result = await db.execute(select(Contest).where(Contest.id == contest_id))
    contest = result.scalars().first()
    if not contest:
        raise HTTPException(status_code=404, detail="Contest not found")
    if not contest.is_published:
        raise HTTPException(status_code=404, detail="Contest not found")

    # Per-problem attempt/AC status for current user (when authenticated)
    user_problem_stats = {}
    if current_user:
        sub_result = await db.execute(
            select(ProblemVersion.problem_id, Submission.status).select_from(Submission)
            .join(ProblemVersion, ProblemVersion.id == Submission.problem_version_id)
            .where(
                Submission.user_id == current_user.id,
                Submission.contest_id == contest_id,
            )
        )
        for row in sub_result.all():
            pid, status = row[0], row[1]
            if pid not in user_problem_stats:
                user_problem_stats[pid] = {"attempts": 0, "solved": False}
            user_problem_stats[pid]["attempts"] += 1
            if status == "AC":
                user_problem_stats[pid]["solved"] = True

    cp_result = await db.execute(
        select(ContestProblem)
        .where(ContestProblem.contest_id == contest_id)
        .order_by(ContestProblem.display_order)
    )
    cps = cp_result.scalars().all()
    problems = []
    for cp in cps:
        p_result = await db.execute(select(Problem).where(Problem.id == cp.problem_id))
        p = p_result.scalars().first()
        if p:
            stats = user_problem_stats.get(p.id, {"attempts": 0, "solved": False})
            problems.append({
                "id": p.id,
                "title": p.title,
                "score": cp.score,
                "display_order": cp.display_order,
                "attempts": stats["attempts"],
                "solved": stats["solved"],
            })

    return {
        "id": contest.id,
        "title": contest.title,
        "description": contest.description or "",
        "start_time": contest.start_time.isoformat() if contest.start_time else None,
        "end_time": contest.end_time.isoformat() if contest.end_time else None,
        "problems": problems,
    }


@router.post("/{contest_id}/register")
async def register_for_contest(
    contest_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    contest_result = await db.execute(select(Contest).where(Contest.id == contest_id))
    contest = contest_result.scalars().first()
    if not contest:
        raise HTTPException(status_code=404, detail="Contest not found")

    reg_stmt = select(ContestRegistration).where(
        ContestRegistration.contest_id == contest_id,
        ContestRegistration.user_id == current_user.id,
    )
    reg_result = await db.execute(reg_stmt)
    if reg_result.scalars().first():
        raise HTTPException(status_code=400, detail="You are already registered for this contest")

    new_reg = ContestRegistration(
        user_id=current_user.id,
        contest_id=contest_id,
        registered_at=datetime.now(pytz.utc),
    )
    db.add(new_reg)
    await db.commit()
    return {"msg": "Successfully registered for the contest", "contest_id": contest_id}


@router.get("/{contest_id}/leaderboard")
async def fetch_leaderboard(contest_id: int):
    if not ws_manager.redis:
        return {"leaderboard": []}
    lb_manager = ContestLeaderboardManager(ws_manager.redis)
    lb_data = await lb_manager.get_live_leaderboard(contest_id=contest_id, limit=100)
    return {"leaderboard": lb_data}


HEARTBEAT_INTERVAL = 15


async def _leaderboard_sse_stream(contest_id: int):
    """Async generator yielding SSE events: snapshot once, then update on Redis pub or every 15s."""
    if not ws_manager.redis:
        yield f"event: snapshot\ndata: {json.dumps({'leaderboard': []})}\n\n"
        return
    lb_manager = ContestLeaderboardManager(ws_manager.redis)
    channel = f"contest:{contest_id}:leaderboard_updates"
    queue = asyncio.Queue()

    async def listener():
        pubsub = ws_manager.redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message.get("type") == "message":
                    raw_data = message["data"]
                    if isinstance(raw_data, bytes):
                        raw_data = raw_data.decode("utf-8")
                    queue.put_nowait({"type": "update", "data": raw_data})
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    async def heartbeat():
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                queue.put_nowait({"type": "heartbeat"})
        except asyncio.CancelledError:
            pass

    # Initial snapshot
    data = await lb_manager.get_live_leaderboard(contest_id=contest_id, limit=100)
    cached_payload = json.dumps({'leaderboard': data})
    yield f"event: snapshot\ndata: {cached_payload}\n\n"

    listener_task = asyncio.create_task(listener())
    heartbeat_task = asyncio.create_task(heartbeat())
    try:
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_INTERVAL + 2)
            except asyncio.TimeoutError:
                msg = {"type": "heartbeat"}
            
            if msg.get("type") == "heartbeat":
                # Keep alive the connection with the last known snapshot
                yield f"event: update\ndata: {cached_payload}\n\n"
            else:
                # Update local cache and stream fresh JSON sent directly from the worker (Redis pubsub)
                cached_payload = msg["data"]
                yield f"event: update\ndata: {cached_payload}\n\n"
    finally:
        listener_task.cancel()
        heartbeat_task.cancel()
        try:
            await listener_task
        except asyncio.CancelledError:
            pass
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass


@router.get("/{contest_id}/leaderboard/stream")
async def stream_leaderboard(contest_id: int):
    """Server-Sent Events stream: snapshot on connect, then updates on change or every 15s."""
    return StreamingResponse(
        _leaderboard_sse_stream(contest_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
