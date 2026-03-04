from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

from server.config import DATABASE_URL

# Create the async engine
# Note: we are using asyncpg, so the URL must start with postgresql+asyncpg://
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL query logging in development
)

# Create an async session maker
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Declarative base class for models
Base = declarative_base()

async def get_db_session():
    """Dependency injection generator to yield DB sessions to FastAPI routes."""
    async with async_session_maker() as session:
        yield session
