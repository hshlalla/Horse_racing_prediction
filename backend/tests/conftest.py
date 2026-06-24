import pytest
import pytest_asyncio
from testcontainers.postgres import PostgresContainer
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.db.base import Base
from app.core.config import Settings

# Initialize test settings that will be used throughout tests
_TEST_SETTINGS = Settings(
    DATABASE_URL="postgresql+asyncpg://test:test@localhost/test",
    REDIS_URL="redis://localhost:6379/0",
    JWT_SECRET="test-secret-key-32-characters-long!",
    ENVIRONMENT="testing",
    FIREBASE_CREDENTIALS_PATH="",
    CRAWL_USER_AGENT="TestBot/1.0",
    LOG_LEVEL="INFO",
    ENABLE_DOCS=False,
    ACCESS_TOKEN_EXPIRE_MINUTES=15,
    REFRESH_TOKEN_EXPIRE_DAYS=30,
)

# Patch settings at import time
import app.core.config
import app.core.security
app.core.config.settings = _TEST_SETTINGS
app.core.security.settings = _TEST_SETTINGS


@pytest.fixture(scope="session")
def postgres_url():
    with PostgresContainer("postgres:16") as pg:
        raw_url = pg.get_connection_url()
        # testcontainers may return postgresql+psycopg2:// or postgresql://
        url = (
            raw_url
            .replace("postgresql+psycopg2://", "postgresql+asyncpg://")
            .replace("postgresql://", "postgresql+asyncpg://")
        )
        yield url


@pytest_asyncio.fixture(scope="session")
async def engine(postgres_url):
    eng = create_async_engine(postgres_url, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncSession:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()
