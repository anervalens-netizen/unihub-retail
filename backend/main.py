from __future__ import annotations

import os
import pathlib
from contextlib import asynccontextmanager
import logging

from logging_config import attach_db_error_handler, setup_logging

setup_logging()


from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

import sentry_sdk

sentry_dsn = os.getenv("VITE_GLITCHTIP_DSN", os.getenv("SENTRY_DSN"))
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        traces_sample_rate=0.1,
    )
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import validate_required_env_vars
from db.connection import (
    apply_pending_migrations,
    close_db_pool,
    ensure_schema_current,
    get_pool,
    init_db_pool,
    prewarm_pool,
)
from auth import require_auth
from routers import agents, campaigns, crm, dashboard, filters, hr, imports, salarii, stores, tasks, visits_report
from services.dashboard_specials import prewarm_special_cards_cache
from services.visits_sync import sync_visits_snapshot

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_required_env_vars()
    await init_db_pool()
    current_pool = await get_pool()
    attach_db_error_handler(current_pool)
    schema_applied = await ensure_schema_current()
    logger.info("Database schema %s", "applied" if schema_applied else "already current")
    migrations = await apply_pending_migrations()
    if migrations:
        logger.info("Applied %d migrations: %s", len(migrations), ", ".join(migrations))
    else:
        logger.info("No pending migrations")
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

_auth = [Depends(require_auth)]

app.include_router(agents.router, dependencies=_auth)
app.include_router(campaigns.router, dependencies=_auth)
app.include_router(dashboard.router, dependencies=_auth)
app.include_router(filters.router, dependencies=_auth)
app.include_router(imports.router, dependencies=_auth)
app.include_router(stores.router, dependencies=_auth)
app.include_router(salarii.router, dependencies=_auth)
app.include_router(visits_report.router, dependencies=_auth)
app.include_router(tasks.router, dependencies=_auth)
app.include_router(hr.router, dependencies=_auth)
app.include_router(crm.router, dependencies=_auth)


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
