import time
import redis.asyncio as aioredis
from fastapi import Request, HTTPException, status
from app.core.config import settings

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL)
    return _redis


async def auth_rate_limit(request: Request) -> None:
    """10 requests per minute per IP on /auth/* endpoints."""
    client_ip = request.client.host if request.client else "unknown"
    key = f"rl:auth:{client_ip}"
    r = _get_redis()
    pipe = r.pipeline()
    now = int(time.time())
    window_start = now - 60
    await pipe.zremrangebyscore(key, 0, window_start)
    await pipe.zadd(key, {str(now): now})
    await pipe.zcard(key)
    await pipe.expire(key, 60)
    results = await pipe.execute()
    count = results[2]
    if count > 10:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")
