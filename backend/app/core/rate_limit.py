import time
import uuid
from typing import Optional

import redis.asyncio as aioredis
import structlog
from fastapi import Request

from app.core.config import settings

log = structlog.get_logger()

# Allow at most RATE_LIMIT requests per RATE_WINDOW_SECONDS, per client IP.
RATE_LIMIT = 10
RATE_WINDOW_SECONDS = 60

_redis: Optional[aioredis.Redis] = None


class RateLimitExceeded(Exception):
    """Raised when a client exceeds the auth rate limit."""


def _get_redis() -> Optional[aioredis.Redis]:
    global _redis
    if _redis is None:
        try:
            _redis = aioredis.from_url(settings.REDIS_URL)
        except Exception as exc:  # pragma: no cover - malformed URL only
            log.warning("rate_limit.redis_init_failed", error=str(exc))
            return None
    return _redis


async def auth_rate_limit(request: Request) -> None:
    """Sliding-window rate limit of RATE_LIMIT requests / RATE_WINDOW_SECONDS per IP.

    Fails open: if Redis is unreachable the request is allowed rather than
    taking down the whole auth surface. Raises ``RateLimitExceeded`` when the
    caller exceeds the budget; ``rate_limit_exception_handler`` turns that into
    a 429 with the standard ``{"error": {...}}`` shape.
    """
    r = _get_redis()
    if r is None:
        return

    client_ip = request.client.host if request.client else "unknown"
    key = f"rl:auth:{client_ip}"
    now = time.time()
    window_start = now - RATE_WINDOW_SECONDS

    try:
        pipe = r.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zadd(key, {f"{now}:{uuid.uuid4().hex}": now})
        pipe.zcard(key)
        pipe.expire(key, RATE_WINDOW_SECONDS)
        results = await pipe.execute()
        count = results[2]
    except Exception as exc:
        # Redis down / connection refused → allow the request (fail-open).
        log.warning("rate_limit.redis_unavailable", error=str(exc))
        return

    if count > RATE_LIMIT:
        raise RateLimitExceeded()
