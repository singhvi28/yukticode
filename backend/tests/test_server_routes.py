"""
Tests for server/routes.py — FastAPI endpoint behaviour.
Uses httpx TestClient; RabbitMQClient is fully mocked with AsyncMocks so no broker needed.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import json
import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient


SUBMIT_PAYLOAD = {
    "problem_id": 1,
    "language": "cpp",
    "src_code": "int main(){}",
}

RUN_PAYLOAD = {
    "language": "py",
    "time_limit": 5,
    "memory_limit": 128,
    "src_code": "print(42)",
}


from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from server.db.database import Base, get_db_session
from server.db.models import User, Problem

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)

async def override_get_db_session():
    async with TestSessionLocal() as session:
        yield session

@pytest.fixture(autouse=True)
def prepare_database_sync():
    import asyncio
    async def init_db():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with TestSessionLocal() as session:
            # Insert a dummy user and published problem
            u = User(id=1, username="test", email="test@test.com", hashed_password="pw")
            session.add(u)
            p = Problem(
                id=1,
                title="Test",
                author_id=1,
                is_published=True,
                statement="Test statement",
                time_limit_ms=2000,
                memory_limit_mb=256,
            )
            session.add(p)
            await session.commit()
    asyncio.run(init_db())
    yield
    async def drop_db():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    asyncio.run(drop_db())

@pytest.fixture()
def client():
    """TestClient with mocked dependencies."""
    mock_mq = AsyncMock()
    from server.routes import router
    from fastapi import FastAPI
    from server.auth import get_current_user

    async def override_get_current_user():
        return User(id=1, username="test", email="test@test.com")

    app = FastAPI()

    # Attach mock mq to app.state (mirrors lifespan behaviour)
    @app.on_event("startup")
    async def startup():
        app.state.mq = mock_mq

    app.include_router(router)
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db_session] = override_get_db_session

    with TestClient(app) as c:
        c.mock_mq = mock_mq
        yield c


# ---------------------------------------------------------------------------
# /submit
# ---------------------------------------------------------------------------

class TestSubmitEndpoint:
    def test_returns_200(self, client):
        resp = client.post('/submit', json=SUBMIT_PAYLOAD)
        assert resp.status_code == 200

    def test_response_contains_msg_and_submission_id(self, client):
        resp = client.post('/submit', json=SUBMIT_PAYLOAD)
        assert "msg" in resp.json()
        assert "submission_id" in resp.json()

    def test_publish_called_once(self, client):
        client.post('/submit', json=SUBMIT_PAYLOAD)
        client.mock_mq.publish_message.assert_awaited_once()

    def test_publish_receives_correct_exchange(self, client):
        client.post('/submit', json=SUBMIT_PAYLOAD)
        args, kwargs = client.mock_mq.publish_message.call_args
        from server.config import SUBMIT_EXCHANGE
        assert args[0] == SUBMIT_EXCHANGE

    def test_mq_payload_does_not_contain_test_cases_or_src_code(self, client):
        """MQ bloat fix: test_cases and src_code must not be in the MQ payload."""
        client.post('/submit', json=SUBMIT_PAYLOAD)
        _, kwargs = client.mock_mq.publish_message.call_args
        body = kwargs.get("body", {})
        assert "test_cases" not in body, "test_cases must not be in MQ payload (MQ bloat fix)"
        assert "src_code" not in body, "src_code must not be in MQ payload (MQ bloat fix)"
        assert "submission_id" in body

    def test_missing_problem_id_returns_422(self, client):
        payload = {k: v for k, v in SUBMIT_PAYLOAD.items() if k != "problem_id"}
        resp = client.post('/submit', json=payload)
        assert resp.status_code == 422

    def test_oversized_src_code_returns_422(self, client):
        """DoS fix: src_code > 65536 chars must be rejected by Pydantic."""
        payload = {**SUBMIT_PAYLOAD, "src_code": "x" * 65537}
        resp = client.post('/submit', json=payload)
        assert resp.status_code == 422

    def test_unpublished_problem_returns_404(self, client):
        """IDOR fix: submitting to an unpublished problem must return 404."""
        resp = client.post('/submit', json={**SUBMIT_PAYLOAD, "problem_id": 9999})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /run
# ---------------------------------------------------------------------------

class TestRunEndpoint:
    def test_returns_200(self, client):
        resp = client.post('/run', json=RUN_PAYLOAD)
        assert resp.status_code == 200

    def test_response_contains_msg(self, client):
        resp = client.post('/run', json=RUN_PAYLOAD)
        assert "msg" in resp.json()

    def test_publish_called_once(self, client):
        client.post('/run', json=RUN_PAYLOAD)
        client.mock_mq.publish_message.assert_awaited_once()

    def test_publish_receives_correct_exchange(self, client):
        client.post('/run', json=RUN_PAYLOAD)
        args, kwargs = client.mock_mq.publish_message.call_args
        from server.config import RUN_EXCHANGE
        assert args[0] == RUN_EXCHANGE

    def test_returns_200_and_generates_run_id(self, client):
        resp = client.post('/run', json=RUN_PAYLOAD)
        assert resp.status_code == 200
        assert "run_id" in resp.json()

    def test_publish_includes_run_id_matching_response(self, client):
        """Worker looks up data['run_id'] to report verdict via webhook."""
        resp = client.post('/run', json=RUN_PAYLOAD)
        run_id = resp.json()["run_id"]
        args, kwargs = client.mock_mq.publish_message.call_args
        body = kwargs.get("body") or (args[2] if len(args) > 2 else args[1])
        # publish_message(exchange, routing_key, body=...)
        if body is None:
            body = kwargs["body"]
        assert body["run_id"] == run_id
        assert "callback_url" not in body

    def test_oversized_src_code_returns_422(self, client):
        """DoS fix: src_code > 65536 chars must be rejected."""
        payload = {**RUN_PAYLOAD, "src_code": "x" * 65537}
        resp = client.post('/run', json=payload)
        assert resp.status_code == 422


class TestRunBatchEndpoint:
    BATCH_PAYLOAD = {
        "language": "py",
        "time_limit": 2000,
        "memory_limit": 256,
        "src_code": "print(1)",
        "tests": [{"input": " ", "expected_output": "1"}],
    }

    def test_returns_batch_id_and_publishes_it(self, client):
        resp = client.post('/run_batch', json=self.BATCH_PAYLOAD)
        assert resp.status_code == 200
        batch_id = resp.json()["batch_id"]
        args, kwargs = client.mock_mq.publish_message.call_args
        body = kwargs.get("body")
        if body is None and len(args) >= 3:
            body = args[2]
        assert body["batch"] is True
        assert body["batch_id"] == batch_id
        assert "callback_url" not in body

