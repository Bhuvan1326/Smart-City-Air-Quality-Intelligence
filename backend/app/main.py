import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import api_router
from app.api.v1.endpoints.websocket import router as ws_router
from app.core.config import settings
from app.core.csrf import CSRFMiddleware
from app.core.logging import logger, setup_logging
from app.core.middleware import AuditLogMiddleware, RateLimitMiddleware
from app.core.secure_headers import SecurityHeadersMiddleware
from app.workers.scheduler import start_scheduler, stop_scheduler


def _run_alembic_upgrade() -> None:
    """Synchronously run `alembic upgrade head`.

    Runs in a worker thread (see below) because alembic's env.py drives
    its own asyncio.run() internally, which cannot be nested inside the
    already-running event loop of this async lifespan handler.
    """
    from alembic import command
    from alembic.config import Config

    backend_root = Path(__file__).resolve().parent.parent
    alembic_cfg = Config(str(backend_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_root / "db_migrations"))
    command.upgrade(alembic_cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("startup", app=settings.APP_NAME, env=settings.ENVIRONMENT)

    # Run DB migrations. This is now a defense-in-depth safety net, not
    # the primary gating mechanism: the `migrate` one-off service in
    # docker-compose.yml is what actually guarantees the backend service
    # never starts against a database that hasn't been migrated yet (see
    # docker-compose.yml comments on that service). `alembic upgrade
    # head` is idempotent, so running it again here is harmless even
    # after `migrate` has already brought the schema to head.
    try:
        await asyncio.get_running_loop().run_in_executor(None, _run_alembic_upgrade)
        logger.info("migrations.complete")
    except Exception as e:
        logger.error("migrations.failed", error=str(e))

    # Provision the documented demo login accounts in every environment.
    # This is deliberately separate from the development-only full demo
    # dataset: production never receives synthetic stations/readings/etc.
    try:
        from app.core.seeder import ensure_demo_users

        await ensure_demo_users()
    except Exception as e:
        logger.error("seed.demo_users_failed", error=str(e))

    # Seed the full demo dataset only in development.
    if not settings.is_production:
        try:
            from app.core.seeder import seed_all

            await seed_all()
        except Exception as e:
            logger.error("seed.failed", error=str(e))

    # Warm up ML model registry
    try:
        from app.ml.inference import get_model_registry

        registry = get_model_registry()
        logger.info("ml.registry_warmed", has_model=registry._active_model is not None)
    except Exception as e:
        logger.warning("ml.registry_warmup_failed", error=str(e))

    await start_scheduler()

    yield

    await stop_scheduler()
    logger.info("shutdown")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered Urban Air Quality Intelligence Platform for Indian city administrations.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Middleware order matters: outermost runs first on request, last on response
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AuditLogMiddleware)

# Evidence photos (see app.services.evidence_storage) — plain local disk,
# served directly rather than via a paid object-storage/CDN.
Path(settings.MEDIA_ROOT).mkdir(parents=True, exist_ok=True)
app.mount(
    settings.MEDIA_URL_PREFIX, StaticFiles(directory=settings.MEDIA_ROOT), name="media"
)

app.include_router(api_router)
app.include_router(ws_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
async def health_check():
    from sqlalchemy import text

    from app.core.database import engine
    from app.core.redis_client import get_redis

    checks: dict[str, str] = {"api": "ok"}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    try:
        redis = await get_redis()
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    # Check ML model
    try:
        from app.ml.inference import get_model_registry

        reg = get_model_registry()
        checks["ml_model"] = (
            reg._active_version if reg._active_model else "statistical_fallback"
        )
    except Exception:
        checks["ml_model"] = "unavailable"

    all_ok = all(v in ("ok",) or not v.startswith("error") for v in checks.values())
    return JSONResponse(
        status_code=(
            status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE
        ),
        content={
            "status": "healthy" if all_ok else "degraded",
            "checks": checks,
            "version": settings.APP_VERSION,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "unhandled_exception", path=request.url.path, error=str(exc), exc_info=exc
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": "Internal server error",
            "code": "INTERNAL_ERROR",
        },
    )
