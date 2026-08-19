"""
Redis-backed ICPC-style contest leaderboard.
Uses Redis Hashes for per-user problem state and a ZSET for global ranking.
"""
import json
import logging
from datetime import datetime, timezone

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from server.db.models import Contest, ContestProblem, Submission, User

logger = logging.getLogger(__name__)

PENALTY_MINUTES_PER_WA = 20


class ContestLeaderboardManager:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def process_submission(
        self,
        contest_id: int,
        user_id: int,
        username: str,
        problem_id: int,
        problem_score: int,
        status: str,
        submitted_at: datetime,
        contest_start_time: datetime,
    ):
        """
        Called when a contest submission finishes judging.
        """
        if status not in ("AC", "WA", "TLE", "RE", "MLE"):
            return

        user_state_key = f"contest:{contest_id}:user:{user_id}:state"
        leaderboard_key = f"contest:{contest_id}:leaderboard"

        raw_state = await self.redis.hget(user_state_key, str(problem_id))
        prob_state = json.loads(raw_state) if raw_state else {
            "is_ac": False,
            "attempts": 0,
            "penalty": 0,
        }

        if prob_state["is_ac"]:
            return

        if status == "AC":
            prob_state["is_ac"] = True
            minutes_elapsed = int((submitted_at - contest_start_time).total_seconds() / 60)
            prob_state["penalty"] = minutes_elapsed + (prob_state["attempts"] * PENALTY_MINUTES_PER_WA)

            await self.redis.hset(user_state_key, str(problem_id), json.dumps(prob_state))

            await self._update_global_ranking(
                contest_id, user_id, username, problem_score, prob_state["penalty"], leaderboard_key
            )
        else:
            prob_state["attempts"] += 1
            await self.redis.hset(user_state_key, str(problem_id), json.dumps(prob_state))

    async def _update_global_ranking(
        self, contest_id: int, user_id: int, username: str, score_delta: int, penalty_delta: int, lb_key: str
    ):
        user_total_key = f"contest:{contest_id}:user:{user_id}:totals"

        new_score = await self.redis.hincrby(user_total_key, "score", score_delta)
        new_penalty = await self.redis.hincrby(user_total_key, "penalty", penalty_delta)

        await self.redis.hset(user_total_key, "username", username)

        combined_zset_score = (new_score * 1_000_000) - new_penalty
        await self.redis.zadd(lb_key, {str(user_id): combined_zset_score})
        # Notify SSE listeners that leaderboard changed by sending the pre-computed data
        lb_data = await self.get_live_leaderboard(contest_id, limit=100)
        await self.redis.publish(
            f"contest:{contest_id}:leaderboard_updates", 
            json.dumps({"leaderboard": lb_data})
        )

    async def get_live_leaderboard(self, contest_id: int, limit: int = 100):
        lb_key = f"contest:{contest_id}:leaderboard"
        top_users = await self.redis.zrevrange(lb_key, 0, limit - 1, withscores=True)

        leaderboard = []
        for rank, (user_id_str, z_score) in enumerate(top_users):
            user_id = int(user_id_str) if isinstance(user_id_str, str) else int(user_id_str.decode("utf-8"))
            user_total_key = f"contest:{contest_id}:user:{user_id}:totals"
            totals = await self.redis.hgetall(user_total_key)

            if totals is None:
                totals = {}
            username = totals.get("username", totals.get(b"username", "Unknown"))
            if isinstance(username, bytes):
                username = username.decode("utf-8")
            score = totals.get("score", totals.get(b"score", 0))
            penalty = totals.get("penalty", totals.get(b"penalty", 0))
            if isinstance(score, str):
                score = int(score)
            elif isinstance(score, bytes):
                score = int(score.decode("utf-8"))
            if isinstance(penalty, str):
                penalty = int(penalty)
            elif isinstance(penalty, bytes):
                penalty = int(penalty.decode("utf-8"))

            leaderboard.append({
                "rank": rank + 1,
                "user_id": user_id,
                "username": username,
                "score": score,
                "penalty": penalty,
            })

        return leaderboard


async def update_leaderboard_on_verdict(
    redis_client: redis.Redis,
    db: AsyncSession,
    submission_id: int,
    status: str,
):
    """Call after a submission verdict is persisted; updates Redis leaderboard if submission is for a contest."""
    stmt = select(Submission).where(Submission.id == submission_id)
    result = await db.execute(stmt)
    submission = result.scalars().first()
    if not submission or not submission.contest_id:
        return

    user_result = await db.execute(select(User).where(User.id == submission.user_id))
    user = user_result.scalars().first()
    if not user:
        return

    problem_id = submission.problem_id

    contest_result = await db.execute(select(Contest).where(Contest.id == submission.contest_id))
    contest = contest_result.scalars().first()
    if not contest or not contest.start_time:
        return
    start_time = contest.start_time
    if getattr(start_time, "tzinfo", None) is None:
        start_time = start_time.replace(tzinfo=timezone.utc)

    cp_result = await db.execute(
        select(ContestProblem).where(
            ContestProblem.contest_id == submission.contest_id,
            ContestProblem.problem_id == problem_id,
        )
    )
    cp = cp_result.scalars().first()
    problem_score = cp.score if cp else 100

    submitted_at = submission.submitted_at
    if not submitted_at:
        submitted_at = datetime.now(timezone.utc)
    elif getattr(submitted_at, "tzinfo", None) is None:
        submitted_at = submitted_at.replace(tzinfo=timezone.utc)

    manager = ContestLeaderboardManager(redis_client)
    await manager.process_submission(
        contest_id=submission.contest_id,
        user_id=submission.user_id,
        username=user.username,
        problem_id=problem_id,
        problem_score=problem_score,
        status=status,
        submitted_at=submitted_at,
        contest_start_time=start_time,
    )
