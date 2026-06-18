import asyncio
import uuid
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.config import settings
from backend.logging_config import configure_logging, request_id_var
from backend.db.connection import init_db_pool, close_db_pool, get_db_pool
from backend.db.migrations.migrate import run_migrations
from backend.api.routers import stocks, ingest, analytics, query, alerts, jobs, reports, decision, fundamentals, options, portfolio, watchlist, performance, stream, calibration, corporate_actions, paper, weights, india, regime, events, data_quality, ml
from backend.api.limiter import limiter
from backend.api.stream import manager as stream_manager, run_broadcaster

configure_logging(service="api")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.cors_origins.strip() == "*":
        logger.warning(
            "CORS_ORIGINS is set to '*' — all origins allowed. "
            "Set CORS_ORIGINS to a comma-separated list of trusted origins before production."
        )
    await init_db_pool()
    pool = get_db_pool()
    await run_migrations(pool)
    logger.info("DB migrations complete")

    broadcaster = asyncio.create_task(
        run_broadcaster(stream_manager, pool,
                        settings.stream_interval_seconds, settings.stream_max_symbols)
    )
    try:
        yield
    finally:
        broadcaster.cancel()
        try:
            await broadcaster
        except asyncio.CancelledError:
            pass
        await close_db_pool()


app = FastAPI(title="Financial AI Platform", version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    rid = request_id_var.get("-")
    logger.error("Unhandled exception [request_id=%s] %s: %s", rid, type(exc).__name__, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": rid},
    )


@app.middleware("http")
async def request_id_middleware(request: Request, call_next) -> Response:
    rid = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    token = request_id_var.set(rid)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response
    finally:
        request_id_var.reset(token)


app.include_router(stocks.router,    prefix="/v1/stocks",    tags=["stocks"])
app.include_router(ingest.router,    prefix="/v1/ingest",    tags=["ingest"])
app.include_router(analytics.router, prefix="/v1/analytics", tags=["analytics"])
app.include_router(query.router,     prefix="/v1/query",     tags=["rag"])
app.include_router(alerts.router,    prefix="/v1/alerts",    tags=["alerts"])
app.include_router(jobs.router,      prefix="/v1/jobs",      tags=["jobs"])
app.include_router(reports.router,   prefix="/v1/reports",   tags=["reports"])
app.include_router(decision.router,      prefix="/v1/decision",      tags=["decision"])
app.include_router(fundamentals.router, prefix="/v1/fundamentals", tags=["fundamentals"])
app.include_router(options.router,      prefix="/v1/options",      tags=["options"])
app.include_router(portfolio.router,    prefix="/v1/portfolio",    tags=["portfolio"])
app.include_router(watchlist.router,    prefix="/v1/watchlist",    tags=["watchlist"])
app.include_router(performance.router,  prefix="/v1/performance",  tags=["performance"])
app.include_router(calibration.router,  prefix="/v1/calibration",  tags=["calibration"])
app.include_router(corporate_actions.router, prefix="/v1/corporate-actions", tags=["corporate-actions"])
app.include_router(paper.router,        prefix="/v1/paper",        tags=["paper-trading"])
app.include_router(weights.router,      prefix="/v1/weights",      tags=["signal-weights"])
app.include_router(india.router,        prefix="/v1/india",        tags=["india-signals"])
app.include_router(regime.router,       prefix="/v1/regime",       tags=["market-regime"])
app.include_router(events.router,       prefix="/v1/events",       tags=["macro-events"])
app.include_router(data_quality.router, prefix="/v1/data-quality", tags=["data-quality"])
app.include_router(ml.router,           prefix="/v1/ml",           tags=["ml-signal"])
app.include_router(stream.router,       prefix="/v1",              tags=["stream"])


@app.get("/health", tags=["ops"])
async def health():
    """Liveness probe — always returns 200 if process is alive."""
    return {"status": "ok"}


@app.get("/ready", tags=["ops"])
async def ready():
    """Readiness probe — checks DB connectivity."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {
            "status": "ready",
            "db": "ok",
            "pool_size": pool.get_size(),
            "pool_free": pool.get_idle_size(),
        }
    except Exception as exc:
        logger.error("Readiness check failed: %s", exc)
        return JSONResponse(status_code=503, content={"status": "unavailable", "db": str(exc)})
