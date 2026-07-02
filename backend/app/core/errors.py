from fastapi import Request
from fastapi.responses import JSONResponse


def error_response(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


async def rate_limit_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return error_response(
        "RATE_LIMIT_EXCEEDED",
        "Too many requests. Please try again later.",
        429,
    )


async def overflow_exception_handler(request: Request, exc: OverflowError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "UNPROCESSABLE_ENTITY", "message": "Integer value too large."}},
    )

async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    import structlog, uuid
    log = structlog.get_logger()
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    log.error("unhandled_exception", request_id=request_id, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL", "message": f"Request ID: {request_id}"}},
    )
