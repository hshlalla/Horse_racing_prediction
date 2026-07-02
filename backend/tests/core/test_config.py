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


def _run_import_config(env: dict, tmp_path):
    """Import app.core.config in a fresh interpreter with a controlled env.

    Runs in tmp_path (no .env present) with only the given environment so the
    module-level ``settings = get_settings()`` is exercised in isolation.
    """
    import subprocess
    import sys

    code = (
        "import app.core.config as c\n"
        "assert c.settings is not None, 'settings is None'\n"
        "assert type(c.settings).__name__ == 'Settings'\n"
        "print('OK')\n"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )


def test_config_module_settings_loaded_when_env_present(tmp_path):
    """With required env vars set, the module-level `settings` is a real Settings."""
    env = {
        "PATH": os.environ["PATH"],
        "DATABASE_URL": "postgresql+asyncpg://u:p@h/db",
        "REDIS_URL": "redis://localhost:6379/0",
        "JWT_SECRET": "supersecret32charslong!!!!!!!!",
        "ENVIRONMENT": "testing",
    }
    result = _run_import_config(env, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_config_import_fails_loudly_without_required_env(tmp_path):
    """Missing required env must raise at import, not silently set settings=None.

    The old ``try/except -> settings = None`` swallowed configuration errors,
    turning them into confusing AttributeErrors later (e.g. settings.LOG_LEVEL).
    Importing config without required vars must fail loudly instead.
    """
    env = {"PATH": os.environ["PATH"]}  # no DATABASE_URL / REDIS_URL / JWT_SECRET
    result = _run_import_config(env, tmp_path)
    assert result.returncode != 0, (
        "importing config without required env must fail loudly, "
        f"got returncode 0. stdout={result.stdout!r}"
    )
    assert "validation error" in result.stderr.lower(), result.stderr
