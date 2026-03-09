"""
Tests for server/routes.py — FastAPI endpoint behaviour.
Uses httpx TestClient; RabbitMQClient is fully mocked with AsyncMocks so no broker needed.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import patch, AsyncMock
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
    "callback_url": "http://localhost:8080/cb",
}


import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from server.db.database import Base, get_db_session
from server.db.models import User, Problem, ProblemVersion

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
            # Insert a dummy user and problem
            u = User(id=1, username="test", email="test@test.com", hashed_password="pw")
            session.add(u)
            p = Problem(id=1, title="Test", author_id=1, is_published=True)
            session.add(p)
            pv = ProblemVersion(id=1, problem_id=1, version_number=1, statement_url="url", time_limit_ms=2000, memory_limit_mb=256, test_data_path="path")
            session.add(pv)
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
    with patch('server.routes.mq', mock_mq), \
         patch('server.routes.upload_text', return_value="mock_code_url"), \
         patch('server.routes.download_text', return_value="mock_statement_md"):
        from server.routes import router
        from fastapi import FastAPI
        from server.auth import get_current_user
        
        async def override_get_current_user():
            return User(id=1, username="test", email="test@test.com")
            
        app = FastAPI()
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

    def test_response_contains_msg(self, client):
        resp = client.post('/submit', json=SUBMIT_PAYLOAD)
        assert "msg" in resp.json()

    def test_publish_called_once(self, client):
        client.post('/submit', json=SUBMIT_PAYLOAD)
        client.mock_mq.publish_message.assert_awaited_once()

    def test_publish_receives_correct_exchange(self, client):
        client.post('/submit', json=SUBMIT_PAYLOAD)
        args, kwargs = client.mock_mq.publish_message.call_args
        from server.config import SUBMIT_EXCHANGE
        assert args[0] == SUBMIT_EXCHANGE

    def test_missing_problem_id_returns_422(self, client):
        payload = {k: v for k, v in SUBMIT_PAYLOAD.items() if k != "problem_id"}
        resp = client.post('/submit', json=payload)
        assert resp.status_code == 422


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

    def test_missing_callback_url_succeeds_and_generates_run_id(self, client):
        payload = {k: v for k, v in RUN_PAYLOAD.items() if k != "callback_url"}
        resp = client.post('/run', json=payload)
        assert resp.status_code == 200
        assert "run_id" in resp.json()
