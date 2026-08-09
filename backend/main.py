from __future__ import annotations

import os
import pathlib
import time
from contextlib import asynccontextmanager
import logging

from dotenv import find_dotenv, load_dotenv
load_dotenv(find_dotenv())

from logging_config import attach_db_error_handler, detach_db_error_handler, setup_logging

setup_logging()


from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from prometheus_client import Counter, Histogram

from config import get_cors_origins, validate_required_env_vars
from db.connection import (
    close_db_pool,
    get_pool,
    init_db_pool,
    prewarm_pool,
)
from db.migration_runner import verify_migrations_current
from auth import require_auth
from oidc_verifier import close_oidc_runtime, init_oidc_runtime
from permissions import (
    require_import_admin,
    require_management_access,
    require_report_export_access,
    require_salary_access,
)
from rate_limits import close_rate_limit_runtime, init_rate_limit_runtime
from session_auth import (
    authenticate_session,
    callback_router as session_callback_router,
    close_session_runtime,
    init_session_runtime,
    router as session_router,
)
from routers import ai_forecast, agents, campaigns, contests, crm, dashboard, exports, filters, grile, health, hr, imports, salarii, store_pnl, stores, target_calculator, tasks, visits_report
from services.jobs import close_arq_pool, get_arq_pool
from observability.prometheus import (
    canonical_handler,
    mark_current_process_dead,
    metrics_payload,
    validate_multiprocess_directory,
)
from observability.error_tracking import configure_error_tracking
from observability.metrics_network import metrics_peer_allowed
from request_context import (
    REQUEST_ID_HEADER,
    RequestContextMiddleware,
    bind_request_id,
    normalize_request_id,
    reset_request_id,
)

configure_error_tracking()

logger = logging.getLogger(__name__)

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests grouped by method, status class and handler.",
    ("method", "status", "handler"),
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds grouped by method, status class and handler.",
    ("method", "status", "handler"),
)
HTTP_SLOW_REQUESTS_TOTAL = Counter(
    "http_slow_requests_total",
    "Requests that exceeded the low-volume latency guardrail.",
    ("method", "status", "handler"),
)
SLOW_REQUEST_THRESHOLD_SECONDS = 3.0
_PROBE_HANDLERS = {"/health", "/readyz", "/livez", "/metrics"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.runtime_config = validate_required_env_vars("web")
    validate_multiprocess_directory()
    try:
        await init_oidc_runtime()
        await init_session_runtime()
        await init_rate_limit_runtime()
        await init_db_pool()
        current_pool = await get_pool()
        attach_db_error_handler(current_pool)
        await verify_migrations_current(current_pool)
        logger.info("Database migrations verified current (read-only)")
        await prewarm_pool()
        arq_pool = await get_arq_pool()
        if arq_pool is None:
            logger.warning("arq worker pool unavailable; queue endpoints degraded")
        else:
            logger.info("arq worker pool initialized")
        yield
    finally:
        try:
            await close_arq_pool()
        finally:
            try:
                await detach_db_error_handler()
            finally:
                try:
                    await close_db_pool()
                finally:
                    try:
                        await close_rate_limit_runtime()
                    finally:
                        try:
                            await close_session_runtime()
                        finally:
                            try:
                                await close_oidc_runtime()
                            finally:
                                mark_current_process_dead()


app = FastAPI(
    title="UniHub API",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# Composition root: auth depends on an application-provided session adapter,
# never on the concrete session module.
app.state.session_authenticator = authenticate_session


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        started_at = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            if request.url.path != "/metrics":
                handler = canonical_handler(request.scope)
                labels = (request.method, "5xx", handler)
                duration = time.perf_counter() - started_at
                HTTP_REQUESTS_TOTAL.labels(*labels).inc()
                HTTP_REQUEST_DURATION_SECONDS.labels(*labels).observe(duration)
                if handler not in _PROBE_HANDLERS and duration >= SLOW_REQUEST_THRESHOLD_SECONDS:
                    HTTP_SLOW_REQUESTS_TOTAL.labels(*labels).inc()
                    logger.warning(
                        "slow request completed with exception",
                        extra={
                            "method": request.method,
                            "path": handler,
                            "status": "5xx",
                            "duration_ms": round(duration * 1000, 1),
                        },
                    )
            raise
        for name, value in getattr(request.state, "rate_limit_headers", {}).items():
            response.headers[name] = value
        if request.url.path != "/metrics":
            handler = canonical_handler(request.scope)
            status = f"{response.status_code // 100}xx"
            labels = (request.method, status, handler)
            duration = time.perf_counter() - started_at
            HTTP_REQUESTS_TOTAL.labels(*labels).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(*labels).observe(duration)
            if handler not in _PROBE_HANDLERS and duration >= SLOW_REQUEST_THRESHOLD_SECONDS:
                HTTP_SLOW_REQUESTS_TOTAL.labels(*labels).inc()
                logger.warning(
                    "slow request completed",
                    extra={
                        "method": request.method,
                        "path": handler,
                        "status": status,
                        "duration_ms": round(duration * 1000, 1),
                    },
                )
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cross-Origin-Embedder-Policy", "credentialless")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "style-src-elem 'self'; "
            "style-src-attr 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "font-src 'self' data:; "
            "connect-src 'self' https://auth.unihub.ro https://errors.unihub.ro; "
            "object-src 'none'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "upgrade-insecure-requests",
        )
        path = request.url.path
        if path.startswith("/assets/"):
            response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
        elif path.startswith(("/api/", "/salarii", "/auth/session")):
            response.headers["Cache-Control"] = "private, no-store, max-age=0"
            response.headers["CDN-Cache-Control"] = "no-store"
            response.headers["Surrogate-Control"] = "no-store"
        elif (
            path == "/"
            or path.endswith(".html")
            or path in ("/sw.js", "/registerSW.js", "/manifest.webmanifest")
        ):
            response.headers.setdefault("Cache-Control", "no-cache, no-store, must-revalidate")
            response.headers.setdefault("CDN-Cache-Control", "no-store")
            response.headers.setdefault("Surrogate-Control", "no-store")
        return response


app.add_middleware(SecurityHeadersMiddleware)

cors_origins = get_cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token", "Accept", "sentry-trace", "baggage", REQUEST_ID_HEADER],
    expose_headers=[REQUEST_ID_HEADER],
)
app.add_middleware(RequestContextMiddleware)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", normalize_request_id(None))
    token = bind_request_id(request_id)
    try:
        logger.error(
            "unhandled request exception",
            extra={"method": request.method, "path": request.url.path},
            exc_info=(type(exc), exc, exc.__traceback__),
        )
    finally:
        reset_request_id(token)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers={REQUEST_ID_HEADER: request_id},
    )


_auth = [Depends(require_auth)]

app.include_router(session_router)
app.include_router(session_callback_router)
app.include_router(health.router)

app.include_router(agents.router, dependencies=_auth)
app.include_router(ai_forecast.router, dependencies=_auth)
app.include_router(campaigns.router, dependencies=_auth)
app.include_router(contests.router, dependencies=_auth)
app.include_router(dashboard.router, dependencies=_auth)
app.include_router(exports.router, dependencies=[Depends(require_report_export_access)])
app.include_router(filters.router, dependencies=_auth)
app.include_router(imports.router, dependencies=[Depends(require_import_admin)])
app.include_router(stores.router, dependencies=_auth)
app.include_router(
    salarii.router,
    dependencies=[Depends(require_salary_access)],
)
app.include_router(visits_report.router, dependencies=_auth)
app.include_router(tasks.router, dependencies=_auth)
app.include_router(hr.router, dependencies=[Depends(require_management_access)])
app.include_router(crm.router, dependencies=_auth)
app.include_router(target_calculator.router, dependencies=[Depends(require_management_access)])
app.include_router(grile.router, dependencies=_auth)
app.include_router(store_pnl.router)


@app.get("/metrics")
async def metrics(request: Request) -> Response:
    """Prometheus-compatible metrics endpoint."""
    peer = request.client.host if request.client else None
    if not metrics_peer_allowed(peer):
        return Response(status_code=404)
    return Response(
        content=metrics_payload(),
        media_type="text/plain; version=0.0.4",
    )


# Serve React SPA static files (production build)
_dist = pathlib.Path(__file__).parent.parent / "dist"
_NO_CACHE = "no-cache, no-store, must-revalidate"
_IMMUTABLE = "public, max-age=31536000, immutable"
_SERVER_NAMESPACES = {
    "api",
    "auth",
    "docs",
    "health",
    "livez",
    "metrics",
    "openapi.json",
    "readyz",
    "redoc",
    "salarii",
}


def spa_fallback_allowed(path: str, scope: dict) -> bool:
    method = str(scope.get("method", "GET")).upper()
    if method not in {"GET", "HEAD"}:
        return False
    first_segment = path.lstrip("/").split("/", 1)[0]
    if first_segment in _SERVER_NAMESPACES or first_segment == "assets":
        return False
    headers = {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in scope.get("headers", [])
    }
    return "text/html" in headers.get("accept", "").lower()

if _dist.exists():
    class SPAStaticFiles(StaticFiles):
        async def get_response(self, path: str, scope):
            try:
                resp = await super().get_response(path, scope)
            except StarletteHTTPException as ex:
                if ex.status_code == 404 and spa_fallback_allowed(path, scope):
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
            # HTML pages should also not be cached
            elif resp.headers.get("content-type", "").startswith("text/html"):
                resp.headers["Cache-Control"] = _NO_CACHE
                resp.headers["CDN-Cache-Control"] = "no-store"
                resp.headers["Surrogate-Control"] = "no-store"
            # Hashed assets are immutable
            elif "/assets/" in path or path.startswith("assets/"):
                resp.headers["Cache-Control"] = _IMMUTABLE
            return resp

    app.mount("/", SPAStaticFiles(directory=_dist, html=True), name="spa")
