from __future__ import annotations

import os
import pathlib
from contextlib import asynccontextmanager
import logging

from logging_config import setup_logging

setup_logging()

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration


def _init_sentry() -> None:
    """Inițializează Sentry dacă SENTRY_DSN e setat. No-op altfel."""
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return
    sentry_sdk.init(
        dsn=dsn,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
            LoggingIntegration(
                level=logging.WARNING,   # breadcrumb din WARNING+
                event_level=logging.ERROR,  # eveniment Sentry din ERROR+
            ),
        ],
        traces_sample_rate=0.1,
        environment=os.getenv("UNIHUB_ENV", "development"),
        release=os.getenv("APP_VERSION", "dev"),
    )


_init_sentry()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from bootstrap import (
    assert_no_default_passwords_in_production,
    ensure_core_users,
    get_core_user_bootstrap_status,
    reset_default_core_users,
    should_reset_default_users_on_boot,
    ensure_tl_users,
    ensure_tl_users_and_assignments,
    should_sync_tl_assignments_on_boot,
)
from config import validate_required_env_vars
from db.connection import (
    apply_pending_migrations,
    close_db_pool,
    ensure_schema_current,
    get_pool,
    init_db_pool,
    prewarm_pool,
)
from routers import admin, agents, ai, auth, campaigns, crm, dashboard, errors, filters, hr, imports, salarii, stores, tasks, visits_report
from services.dashboard_specials import prewarm_special_cards_cache
from services.visits_sync import sync_visits_snapshot

logger = logging.getLogger(__name__)


async def ensure_default_users() -> None:
    pool = await get_pool()

    async with pool.acquire() as conn:
        await ensure_core_users(conn)
        await assert_no_default_passwords_in_production(conn)
        if should_reset_default_users_on_boot():
            reset_users = await reset_default_core_users(conn)
            for row in reset_users:
                logger.warning(
                    "Default user reset on boot for role=%s username=%s",
                    row["role"],
                    row["username"],
                )
        for row in await get_core_user_bootstrap_status(conn):
            logger.info(
                "Default user status role=%s username=%s exists=%s active=%s",
                row["role"],
                row["username"],
                row["exists"],
                row["is_active"],
            )
        await ensure_tl_users(conn)
        if should_sync_tl_assignments_on_boot():
            await ensure_tl_users_and_assignments(conn)


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_required_env_vars()
    await init_db_pool()
    schema_applied = await ensure_schema_current()
    logger.info("Database schema %s", "applied" if schema_applied else "already current")
    migrations = await apply_pending_migrations()
    if migrations:
        logger.info("Applied %d migrations: %s", len(migrations), ", ".join(migrations))
    else:
        logger.info("No pending migrations")
    await ensure_default_users()
    await prewarm_pool()
    current_pool = await get_pool()
    async with current_pool.acquire() as conn:
        synced = await sync_visits_snapshot(conn)
        logger.info("visits_snapshot synced at boot: %d rows", synced)
    prewarm_special_cards_cache()
    yield
    await close_db_pool()


app = FastAPI(title="UniHub API", lifespan=lifespan)

cors_origins = [
    item.strip()
    for item in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if item.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(ai.router)
app.include_router(agents.router)
app.include_router(campaigns.router)
app.include_router(dashboard.router)
app.include_router(filters.router)
app.include_router(imports.router)
app.include_router(stores.router)
app.include_router(salarii.router)
app.include_router(visits_report.router)
app.include_router(tasks.router)
app.include_router(hr.router)
app.include_router(crm.router)
app.include_router(errors.router)


@app.get("/health")
async def health() -> JSONResponse:
    """Readiness probe: verifica pool-ul DB cu SELECT 1.

    Returneaza 200 daca pool-ul raspunde, 503 altfel. Load balancer-ul
    vede diferenta intre "procesul e sus" si "poate servi request-uri".
    """
    try:
        current_pool = await get_pool()
        async with current_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
    except Exception:  # noqa: BLE001 — orice exceptie = unhealthy
        # Log complet pentru diagnoza, dar raspunsul HTTP nu expune detalii
        # (connection string-uri / path-uri pot ajunge la load balancer).
        logger.exception("Health check failed")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy"},
        )
    return JSONResponse(content={"status": "ok"})


# Serve React SPA static files (production build)
_dist = pathlib.Path(__file__).parent.parent / "dist"
_NO_CACHE = "no-cache, no-store, must-revalidate"
_IMMUTABLE = "public, max-age=31536000, immutable"

if _dist.exists():
    class SPAStaticFiles(StaticFiles):
        async def get_response(self, path: str, scope):
            try:
                resp = await super().get_response(path, scope)
            except StarletteHTTPException as ex:
                if ex.status_code == 404:
                    resp = FileResponse(_dist / "index.html")
                    resp.headers["Cache-Control"] = _NO_CACHE
                    resp.headers["CDN-Cache-Control"] = "no-store"
                    resp.headers["Surrogate-Control"] = "no-store"
                    return resp
                raise
            # sw.js and index.html must never be cached (browser + CDN)
            if path in ("sw.js", "index.html", "", "registerSW.js", "manifest.webmanifest"):
                resp.headers["Cache-Control"] = _NO_CACHE
                resp.headers["CDN-Cache-Control"] = "no-store"
                resp.headers["Surrogate-Control"] = "no-store"
            # Hashed assets are immutable
            elif "/assets/" in path or path.startswith("assets/"):
                resp.headers["Cache-Control"] = _IMMUTABLE
            return resp

    app.mount("/", SPAStaticFiles(directory=_dist, html=True), name="spa")
