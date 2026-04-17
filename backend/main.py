import logging
import asyncio
from contextlib import asynccontextmanager
from contextlib import suppress

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.auth import router as auth_router
from api.admin import router as admin_router
from api.containers import router as containers_router
from api.health import router as health_router
from api.mfa import router as mfa_router
from api.preconnect import router as preconnect_router
from api.session_ws import router as session_ws_router
from api.sessions import router as sessions_router
from api.setup_routes import router as setup_router
from config import get_settings
from core.builtin_templates import seed_builtin_templates
from core.limiter import limiter
from core.session_expiry import session_expiry_loop
from db.database import SessionLocal
from middleware.dynamic_cors import DynamicCORSMiddleware
from middleware.request_id import RequestIdMiddleware

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    expiry_task = None
    db = SessionLocal()
    try:
        n = seed_builtin_templates(db)
        if n:
            logger.info("Seeded %d built-in container template(s)", n)
        expiry_task = asyncio.create_task(session_expiry_loop())
    except Exception:
        logger.exception("Startup initialization failed")
        db.rollback()
        raise
    finally:
        db.close()
    try:
        yield
    finally:
        if expiry_task is not None:
            expiry_task.cancel()
            with suppress(asyncio.CancelledError):
                await expiry_task


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.state.limiter = limiter

app.add_middleware(RequestIdMiddleware)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(DynamicCORSMiddleware)

app.include_router(health_router, prefix="/api")
app.include_router(setup_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(mfa_router, prefix="/api")
app.include_router(preconnect_router, prefix="/api")
app.include_router(containers_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(sessions_router, prefix="/api")
app.include_router(session_ws_router)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", "unknown")
    detail = exc.detail
    message = detail if isinstance(detail, str) else str(detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": message,
            "code": f"http_{exc.status_code}",
            "trace_id": trace_id,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", "unknown")
    details = exc.errors()
    msg = "Validation error"
    if details:
        first = details[0]
        msg = str(first.get("msg") or msg)
    return JSONResponse(
        status_code=422,
        content={
            "error": msg,
            "code": "validation_error",
            "trace_id": trace_id,
        },
    )


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, _exc: RateLimitExceeded) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", "unknown")
    return JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded",
            "code": "rate_limited",
            "trace_id": trace_id,
        },
    )
