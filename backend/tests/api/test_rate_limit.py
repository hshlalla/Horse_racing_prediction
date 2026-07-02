import json

import pytest
from testcontainers.redis import RedisContainer

import app.core.rate_limit as rate_limit
from app.core.rate_limit import RATE_LIMIT, RateLimitExceeded, auth_rate_limit


def _req(ip: str):
    """Minimal stand-in for a Starlette Request with a client host."""
    client = type("_Client", (), {"host": ip})()
    return type("_Request", (), {"client": client})()


@pytest.fixture(scope="module")
def redis_url():
    with RedisContainer("redis:7") as rc:
        host = rc.get_container_host_ip()
        port = rc.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"


@pytest.fixture
def real_redis(redis_url, monkeypatch):
    """Point the limiter at a real Redis and reset its cached client."""
    monkeypatch.setattr(rate_limit.settings, "REDIS_URL", redis_url)
    monkeypatch.setattr(rate_limit, "_redis", None)
    yield
    monkeypatch.setattr(rate_limit, "_redis", None)


@pytest.mark.asyncio
async def test_allows_up_to_limit_then_blocks(real_redis):
    req = _req("203.0.113.1")
    for _ in range(RATE_LIMIT):
        await auth_rate_limit(req)  # within budget → no raise
    with pytest.raises(RateLimitExceeded):
        await auth_rate_limit(req)  # one over the limit → blocked


@pytest.mark.asyncio
async def test_separate_ips_have_separate_budgets(real_redis):
    busy = _req("203.0.113.2")
    for _ in range(RATE_LIMIT):
        await auth_rate_limit(busy)
    # A different IP must still be allowed even when another is exhausted.
    await auth_rate_limit(_req("203.0.113.3"))


@pytest.mark.asyncio
async def test_fails_open_when_redis_unavailable(monkeypatch):
    """If Redis is unreachable, the limiter allows the request (fail-open)."""
    monkeypatch.setattr(rate_limit.settings, "REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setattr(rate_limit, "_redis", None)
    # Well beyond the limit, but with no reachable Redis nothing should raise.
    for _ in range(RATE_LIMIT + 5):
        await auth_rate_limit(_req("203.0.113.4"))
    monkeypatch.setattr(rate_limit, "_redis", None)


@pytest.mark.asyncio
async def test_handler_returns_429_error_shape():
    from app.core.errors import rate_limit_exception_handler

    resp = await rate_limit_exception_handler(_req("1.1.1.1"), RateLimitExceeded())
    assert resp.status_code == 429
    body = json.loads(resp.body)
    assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"


def test_app_registers_rate_limit_handler():
    from app.main import create_app

    app = create_app()
    assert RateLimitExceeded in app.exception_handlers
