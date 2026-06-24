import os
import pytest
from app.core.config import Settings


def test_settings_load_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET", "supersecret32charslong!!!!!!!!")
    monkeypatch.setenv("ENVIRONMENT", "testing")
    s = Settings()
    assert s.DATABASE_URL == "postgresql+asyncpg://u:p@h/db"
    assert s.ENVIRONMENT == "testing"
    assert s.is_production is False


def test_settings_production_flag(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost/0")
    monkeypatch.setenv("JWT_SECRET", "supersecret32charslong!!!!!!!!")
    monkeypatch.setenv("ENVIRONMENT", "production")
    s = Settings()
    assert s.is_production is True
