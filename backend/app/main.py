import uuid
from contextlib import asynccontextmanager
from typing import Callable
import structlog
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
import redis.asyncio as aioredis

from app.core.config import settings
from app.core.errors import unhandled_exception_handler
from app.core.logging import configure_logging
from app.db.session import async_session_factory

log = structlog.get_logger()


async def _readyz_check() -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        result["db"] = "ok"
    except Exception:
        result["db"] = "error"
    try:
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        result["redis"] = "ok"
    except Exception:
        result["redis"] = "error"
    return result


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.LOG_LEVEL)
    log.info("startup", environment=settings.ENVIRONMENT)
    
    from app.scheduler.jobs import setup_scheduler, scheduler
    setup_scheduler()
    
    yield
    
    scheduler.shutdown()
    log.info("shutdown")


def create_app() -> FastAPI:
    configure_logging(settings.LOG_LEVEL)

    app = FastAPI(
        title="Horse Racing Prediction API",
        version="1.0.0",
        docs_url="/api/docs" if not settings.is_production or settings.ENABLE_DOCS else None,
        redoc_url="/api/redoc" if not settings.is_production or settings.ENABLE_DOCS else None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # Request ID middleware
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    from app.core.errors import overflow_exception_handler
    app.add_exception_handler(OverflowError, overflow_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # Prometheus metrics
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    # Health endpoints
    @app.get("/healthz", tags=["ops"])
    async def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/readyz", tags=["ops"])
    async def readyz() -> dict:
        return await _readyz_check()

    # API routers (added in later tasks)
    from app.api.v1 import router as v1_router
    app.include_router(v1_router, prefix="/api/v1")

    # Static web app — served last so API routes take priority
    import pathlib
    static_dir = pathlib.Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


app = create_app()
