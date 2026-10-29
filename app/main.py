import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import request_id_ctx, setup_logging
from app.db.session import engine, init_db

setup_logging()
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(application: FastAPI):
    init_db()
    logger.info("application started")
    yield
    logger.info("application stopped")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="企业文档问答后端服务：异步索引 + 向量检索 + 带引用的问答",
    lifespan=lifespan,
)

register_exception_handlers(app)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    token = request_id_ctx.set(request_id)
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["x-request-id"] = request_id
        return response
    finally:
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": status_code,
                "cost_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        request_id_ctx.reset(token)


app.include_router(api_router, prefix="/api/v1")


@app.get("/healthz", tags=["ops"])
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/readyz", tags=["ops"])
def readyz():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception:
        logger.exception("readiness check failed")
        return JSONResponse(status_code=503, content={"status": "not-ready"})


@app.get("/", tags=["ops"])
def root() -> dict:
    return {"name": settings.app_name, "docs": "/docs", "health": "/healthz"}
