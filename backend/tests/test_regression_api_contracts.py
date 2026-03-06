"""
Regression tests for Bug 3 & Bug 5 (HTTP endpoint contract bugs).

Bug 3: /auth/login expects a JSON body (Pydantic UserLogin model).
       test_submission.py was using httpx data= (form-encoded), getting 422.

Bug 5: GET /submissions/{id} requires Bearer auth.
       test_submission.py was polling without the Authorization header, getting 401.

These tests verify the precise API contract so that client scripts like
test_submission.py are guaranteed to work correctly.
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from fastapi import FastAPI

# Import routers fresh — avoid touching the global app.dependency_overrides
from server.routes import router as api_router
from server.auth import router as auth_router, get_current_user
from server.db.database import Base, get_db_session
from server.db.models import User, Problem, ProblemVersion, Submission


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(loop_scope="function")
async def db_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="function")
async def test_app(db_engine):
    """
    A fresh FastAPI app per test with its own in-memory DB and mocked RabbitMQ.
    Avoids polluting the global app.dependency_overrides.
    """
    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db_session():
        async with session_factory() as session:
            yield session

    app = FastAPI()
    app.include_router(api_router)
    app.include_router(auth_router)
    app.dependency_overrides[get_db_session] = override_get_db_session

    # Patch MQ so no broker connection is attempted
    from server.routes import mq
    mq.publish_message = AsyncMock()
    mq.connect = AsyncMock()
    mq.close = AsyncMock()

    yield app

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Bug 3 — /auth/login must accept JSON, not form-encoded data
# ---------------------------------------------------------------------------

class TestLoginEndpointContentType:
    """
    The login endpoint uses a Pydantic body model (UserLogin), so FastAPI
    only accepts application/json. Form-encoded requests must be rejected.
    """

    @pytest.mark.asyncio
    async def test_login_with_json_body_succeeds(self, test_app):
        """Regression: test_submission.py must use json=, not data=."""
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            await client.post("/auth/register", json={
                "username": "alice", "email": "alice@example.com", "password": "pass123"
            })
            resp = await client.post("/auth/login", json={
                "username": "alice", "password": "pass123"
            })
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    @pytest.mark.asyncio
    async def test_login_with_form_data_is_rejected(self, test_app):
        """
        Sending form-encoded data (httpx data=...) to a Pydantic body endpoint
        yields 422. This is exactly what the old test_submission.py did.
        """
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            await client.post("/auth/register", json={
                "username": "bob", "email": "bob@example.com", "password": "pass123"
            })
            resp = await client.post(
                "/auth/login",
                content="username=bob&password=pass123",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        assert resp.status_code == 422, (
            "Login endpoint must reject form-encoded bodies with 422 — "
            "it only accepts application/json (Pydantic model)."
        )

    @pytest.mark.asyncio
    async def test_login_returns_access_token_and_user_id(self, test_app):
        """Token response shape must contain all fields test_submission.py relies on."""
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            await client.post("/auth/register", json={
                "username": "carol", "email": "carol@example.com", "password": "pass123"
            })
            resp = await client.post("/auth/login", json={
                "username": "carol", "password": "pass123"
            })
        data = resp.json()
        assert "access_token" in data
        assert "token_type" in data
        assert data["token_type"] == "bearer"


# ---------------------------------------------------------------------------
# Bug 5 — GET /submissions/{id} requires Authorization header
# ---------------------------------------------------------------------------

class TestSubmissionPollingRequiresAuth:
    """
    Polling /submissions/{id} without a Bearer token must return 401.
    Including a valid token must return 200 with submission data.
    """

    @pytest.mark.asyncio
    async def test_poll_without_auth_returns_401(self, test_app):
        """Regression: old test_submission.py forgot headers= on the polling call."""
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.get("/submissions/999")
        assert resp.status_code == 401, (
            "GET /submissions/{id} must return 401 when no Bearer token is provided. "
            "test_submission.py was polling without headers= and silently getting 401."
        )

    @pytest.mark.asyncio
    async def test_poll_with_auth_and_valid_id_returns_200(self, test_app, db_engine):
        """Polling with a valid token for an owned submission must return 200."""
        session_factory = async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            await client.post("/auth/register", json={
                "username": "dave", "email": "dave@example.com", "password": "pass123"
            })
            login_resp = await client.post("/auth/login", json={
                "username": "dave", "password": "pass123"
            })
            token = login_resp.json()["access_token"]
            user_id = login_resp.json()["user_id"]
            headers = {"Authorization": f"Bearer {token}"}

            async with session_factory() as session:
                problem = Problem(title="Dave's Problem", author_id=user_id, is_published=True)
                session.add(problem)
                await session.flush()
                pv = ProblemVersion(
                    problem_id=problem.id, version_number=1,
                    statement_url="s3://bucket/stmt.md",
                    time_limit_ms=2000, memory_limit_mb=256,
                    test_data_path="/test_data/p1",
                )
                session.add(pv)
                await session.flush()
                sub = Submission(
                    user_id=user_id, problem_version_id=pv.id,
                    language="py", code_url="s3://bucket/code.py", status="PENDING",
                )
                session.add(sub)
                await session.commit()
                await session.refresh(sub)
                sub_id = sub.id

            resp = await client.get(f"/submissions/{sub_id}", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == sub_id
        assert data["status"] == "PENDING"

    @pytest.mark.asyncio
    async def test_poll_with_auth_for_other_users_submission_returns_404(self, test_app, db_engine):
        """User A must not be able to read User B's submission even with a valid token."""
        session_factory = async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            await client.post("/auth/register", json={
                "username": "eve", "email": "eve@example.com", "password": "pass123"
            })
            await client.post("/auth/register", json={
                "username": "frank", "email": "frank@example.com", "password": "pass123"
            })
            eve_token = (await client.post("/auth/login", json={
                "username": "eve", "password": "pass123"
            })).json()["access_token"]
            frank_id = (await client.post("/auth/login", json={
                "username": "frank", "password": "pass123"
            })).json()["user_id"]

            async with session_factory() as session:
                problem = Problem(title="Frank's Problem", author_id=frank_id, is_published=True)
                session.add(problem)
                await session.flush()
                pv = ProblemVersion(
                    problem_id=problem.id, version_number=1,
                    statement_url="s3://bucket/stmt.md",
                    time_limit_ms=2000, memory_limit_mb=256,
                    test_data_path="/test_data/p2",
                )
                session.add(pv)
                await session.flush()
                sub = Submission(
                    user_id=frank_id, problem_version_id=pv.id,
                    language="py", code_url="s3://bucket/code.py", status="AC",
                )
                session.add(sub)
                await session.commit()
                await session.refresh(sub)
                sub_id = sub.id

            resp = await client.get(
                f"/submissions/{sub_id}",
                headers={"Authorization": f"Bearer {eve_token}"},
            )
        assert resp.status_code == 404, "Cross-user submission access must return 404"
