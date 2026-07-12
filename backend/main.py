from __future__ import annotations

import os
import pathlib
import time
import json
from contextlib import asynccontextmanager
import logging

from dotenv import find_dotenv, load_dotenv
load_dotenv(find_dotenv())

from logging_config import attach_db_error_handler, detach_db_error_handler, setup_logging

setup_logging()


from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import httpx

import sentry_sdk
from request_context import (
    REQUEST_ID_HEADER,
    RequestContextMiddleware,
    bind_request_id,
    get_request_id,
    normalize_request_id,
    reset_request_id,
)

sentry_dsn = os.getenv("VITE_GLITCHTIP_DSN", os.getenv("SENTRY_DSN"))
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        traces_sample_rate=0.1,
    )
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from prometheus_client import REGISTRY, Counter, Histogram, generate_latest

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
from oidc_verifier import close_oidc_runtime, init_oidc_runtime
from permissions import (
    require_import_admin,
    require_management_access,
    require_report_export_access,
    require_salary_access,
)
from rate_limits import (
    AUTH_PROXY_LIMIT,
    anonymous_rate_limit,
    close_rate_limit_runtime,
    init_rate_limit_runtime,
)
from routers import ai_forecast, agents, campaigns, contests, crm, dashboard, exports, filters, grile, hr, imports, salarii, store_pnl, stores, target_calculator, tasks, visits_report
from services.dashboard_specials import prewarm_special_cards_cache
from services.retail_metrics import update_business_metrics
from services.visits_sync import sync_visits_snapshot
from services.jobs import close_arq_pool, get_arq_pool

logger = logging.getLogger(__name__)
AUTH_PROXY_BASE_URL = os.getenv("AUTH_PROXY_BASE_URL", "https://auth.unihub.ro").rstrip("/")

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


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_required_env_vars()
    try:
        await init_oidc_runtime()
        await init_rate_limit_runtime()
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
        await get_arq_pool()
        logger.info("arq worker pool initialized")
        current_pool = await get_pool()
        await update_business_metrics(current_pool)
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
                        await close_oidc_runtime()


app = FastAPI(title="UniHub API", lifespan=lifespan)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        started_at = time.perf_counter()
        response = await call_next(request)
        for name, value in getattr(request.state, "rate_limit_headers", {}).items():
            response.headers[name] = value
        if request.url.path != "/metrics":
            route = request.scope.get("route")
            handler = getattr(route, "path", request.url.path)
            status = f"{response.status_code // 100}xx"
            labels = (request.method, status, handler)
            HTTP_REQUESTS_TOTAL.labels(*labels).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(*labels).observe(time.perf_counter() - started_at)
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
            "connect-src 'self' https://auth.unihub.ro; "
            "object-src 'none'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "upgrade-insecure-requests",
        )
        path = request.url.path
        if path.startswith("/assets/"):
            response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
        elif (
            path.startswith("/api/")
            or path == "/"
            or path.endswith(".html")
            or path in ("/sw.js", "/registerSW.js", "/manifest.webmanifest")
        ):
            response.headers.setdefault("Cache-Control", "no-cache, no-store, must-revalidate")
            response.headers.setdefault("CDN-Cache-Control", "no-store")
            response.headers.setdefault("Surrogate-Control", "no-store")
        return response


app.add_middleware(SecurityHeadersMiddleware)

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
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept", "sentry-trace", "baggage", REQUEST_ID_HEADER],
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


@app.get("/metrics")
async def metrics() -> Response:
    """Prometheus-compatible metrics endpoint."""
    return Response(
        content=generate_latest(REGISTRY),
        media_type="text/plain; version=0.0.4",
    )


@app.api_route(
    "/auth/proxy/{path:path}",
    methods=["GET", "POST"],
    dependencies=[Depends(anonymous_rate_limit(AUTH_PROXY_LIMIT))],
)
async def auth_proxy(path: str, request: Request) -> Response:
    """Proxy requests to authentik.

    For token endpoint requests, injects the client_secret (confidential
    client) since SPAs cannot safely store secrets.
    """
    target = f"{AUTH_PROXY_BASE_URL}/{path}"
    params = dict(request.query_params)
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "origin", "referer")}
    headers[REQUEST_ID_HEADER] = get_request_id() or normalize_request_id(request.headers.get(REQUEST_ID_HEADER))
    body = await request.body()

    # Inject client_secret for token endpoint (confidential client)
    if path == "application/o/token/" and request.method == "POST":
        from urllib.parse import parse_qs, urlencode
        body_str = body.decode("utf-8")
        body_params = parse_qs(body_str)
        client_secret = os.getenv("OIDC_CLIENT_SECRET") or os.getenv("AUTHENTIK_CLIENT_SECRET")
        if not client_secret:
            logger.error("OIDC client secret is not configured")
            raise HTTPException(status_code=500, detail="OIDC proxy is not configured")
        body_params["client_secret"] = [client_secret]
        body = urlencode(body_params, doseq=True).encode("utf-8")
        headers["content-type"] = "application/x-www-form-urlencoded"
        headers["content-length"] = str(len(body))

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
        resp = await client.request(
            method=request.method,
            url=target,
            params=params if params else None,
            headers=headers,
            content=body if body else None,
        )
    content = resp.content
    # Rewrite discovery response to route API calls through the proxy
    # (token/userinfo/etc — avoids CORS + injects client_secret)
    if path.endswith("/.well-known/openid-configuration"):
        origin = request.headers.get("origin")
        if not origin:
            host = request.headers.get("host", request.url.netloc)
            # CloudFlare forwards internally over HTTP — always use HTTPS for public URLs
            scheme = "http" if host.startswith("localhost") or host.startswith("127.") else "https"
            origin = f"{scheme}://{host}"
        try:
            discovery = json.loads(content.decode("utf-8"))
        except json.JSONDecodeError:
            logger.warning("OIDC discovery response is not valid JSON")
        else:
            for endpoint_key in ("token_endpoint", "userinfo_endpoint"):
                endpoint = discovery.get(endpoint_key)
                if isinstance(endpoint, str) and endpoint.startswith(AUTH_PROXY_BASE_URL):
                    proxied_path = endpoint.removeprefix(AUTH_PROXY_BASE_URL).lstrip("/")
                    discovery[endpoint_key] = f"{origin}/auth/proxy/{proxied_path}"
            # Do NOT rewrite authorization_endpoint — browser must redirect there directly.
            content = json.dumps(discovery).encode("utf-8")
    response_headers = {
        k: v for k, v in resp.headers.items()
        if k.lower() not in ("transfer-encoding", "content-encoding", "content-length")
    }
    if resp.is_redirect and "location" in resp.headers:
        response_headers["location"] = resp.headers["location"]
    else:
        response_headers["content-type"] = resp.headers.get("content-type", "application/json")
    return Response(
        content=content,
        status_code=resp.status_code,
        headers=response_headers,
    )


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
