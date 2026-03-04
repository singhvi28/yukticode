import pytest
import pytest_asyncio
from unittest.mock import AsyncMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from server.main import app
from server.db.database import Base, get_db_session

# Use in-memory SQLite for testing to avoid touching real DB
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)

async def override_get_db_session():
    async with TestSessionLocal() as session:
        yield session

app.dependency_overrides[get_db_session] = override_get_db_session

@pytest_asyncio.fixture(loop_scope="function", autouse=True)
async def mock_rabbitmq(monkeypatch):
    """Mock out RabbitMQ for auth routes to prevent network side-effects/hangs."""
    monkeypatch.setattr("server.routes.mq.connect", AsyncMock())
    monkeypatch.setattr("server.routes.mq.close", AsyncMock())
    monkeypatch.setattr("server.routes.mq.publish_message", AsyncMock())


@pytest_asyncio.fixture(loop_scope="function", autouse=True)
async def prepare_database():
    """Setup and teardown the in-memory database for each test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest.mark.asyncio
async def test_register_user():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/auth/register",
            json={"username": "testuser", "email": "test@example.com", "password": "securepassword"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
        assert data["email"] == "test@example.com"
        assert "id" in data


@pytest.mark.asyncio
async def test_login_user():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # First register
        await client.post(
            "/auth/register",
            json={"username": "testuser", "email": "test@example.com", "password": "securepassword"}
        )
        
        # Then login
        response = await client.post(
            "/auth/login",
            json={"username": "testuser", "password": "securepassword"}
        )
        assert response.status_code == 200
        assert "access_token" in response.json()

@pytest.mark.asyncio
async def test_login_invalid_password():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # First register
        await client.post(
            "/auth/register",
            json={"username": "testuser", "email": "test@example.com", "password": "securepassword"}
        )
        
        # Then login with wrong password
        response = await client.post(
            "/auth/login",
            json={"username": "testuser", "password": "wrongpassword"}
        )
        assert response.status_code == 401
