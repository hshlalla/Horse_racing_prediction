import pytest
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
