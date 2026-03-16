"""
Tests for server/routes.py — FastAPI endpoint behaviour.
Uses httpx TestClient; RabbitMQClient is fully mocked with AsyncMocks so no broker needed.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import hashlib
import hmac
import json
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
            # Insert a dummy user and published problem
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
    with patch('server.routes.upload_text', return_value="mock_code_url"), \
         patch('server.routes.download_text', return_value="mock_statement_md"):
        from server.routes import router
        from fastapi import FastAPI, Request
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

    def test_missing_callback_url_succeeds_and_generates_run_id(self, client):
        payload = {k: v for k, v in RUN_PAYLOAD.items() if k != "callback_url"}
        resp = client.post('/run', json=payload)
        assert resp.status_code == 200
        assert "run_id" in resp.json()

    def test_oversized_src_code_returns_422(self, client):
        """DoS fix: src_code > 65536 chars must be rejected."""
        payload = {**RUN_PAYLOAD, "src_code": "x" * 65537}
        resp = client.post('/run', json=payload)
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /webhook/submit — HMAC verification
# ---------------------------------------------------------------------------

class TestWebhookAuth:
    WEBHOOK_PAYLOAD = {"status": "AC", "execution_time_ms": 100.0, "peak_memory_mb": 32.0}

    def _make_sig(self, secret: str, body: bytes) -> str:
        return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    def test_webhook_passes_with_no_secret_configured(self, client):
        """When WEBHOOK_SECRET is empty (dev mode), any request is accepted."""
        resp = client.post('/webhook/submit/1', json=self.WEBHOOK_PAYLOAD)
        assert resp.status_code == 200

    def test_webhook_rejects_wrong_signature(self, client):
        """Unprotected webhook fix: wrong signature must return 403."""
        body = json.dumps(self.WEBHOOK_PAYLOAD).encode()
        with patch('server.routes.WEBHOOK_SECRET', 'supersecret'):
            resp = client.post(
                '/webhook/submit/1',
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": "sha256=deadbeef",
                },
            )
        assert resp.status_code == 403

    def test_webhook_accepts_correct_signature(self, client):
        """Correct HMAC signature must be accepted."""
        body = json.dumps(self.WEBHOOK_PAYLOAD).encode()
        secret = "supersecret"
        sig = self._make_sig(secret, body)
        with patch('server.routes.WEBHOOK_SECRET', secret):
            resp = client.post(
                '/webhook/submit/1',
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": sig,
                },
            )
        assert resp.status_code == 200

    def test_webhook_rejects_missing_signature_when_secret_set(self, client):
        """No signature header with a configured secret must return 403."""
        body = json.dumps(self.WEBHOOK_PAYLOAD).encode()
        with patch('server.routes.WEBHOOK_SECRET', 'supersecret'):
            resp = client.post(
                '/webhook/submit/1',
                content=body,
                headers={"Content-Type": "application/json"},
            )
        assert resp.status_code == 403
