from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str
    REDIS_URL: str
    JWT_SECRET: str
    ENVIRONMENT: str = "development"
    FIREBASE_CREDENTIALS_PATH: str = ""
    CRAWL_USER_AGENT: str = "HorseRaceBot/1.0"
    LOG_LEVEL: str = "INFO"
    ENABLE_DOCS: bool = False

    # JWT
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


try:
    settings = get_settings()
except Exception:
    # During testing, settings may not be available at import time
    settings = None
