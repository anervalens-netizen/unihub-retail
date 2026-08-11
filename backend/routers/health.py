from __future__ import annotations

import logging
import time

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram

from services.health import verify_readiness


logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])

READINESS_CHECKS_TOTAL = Counter(
    "readiness_checks_total",
    "Readiness checks grouped by their bounded outcome.",
    ("outcome",),
)
READINESS_CHECK_DURATION_SECONDS = Histogram(
    "readiness_check_duration_seconds",
    "Readiness dependency-check duration in seconds.",
)


@router.get("/livez", include_in_schema=False)
async def liveness() -> JSONResponse:
    """Process-only probe; never touches PostgreSQL, Valkey or OIDC."""
    return JSONResponse(content={"status": "alive"})


@router.get("/health", include_in_schema=False)
@router.get("/readyz", include_in_schema=False)
async def readiness() -> JSONResponse:
    """Bounded probe for PostgreSQL, session storage and OIDC JWKS."""
    started_at = time.perf_counter()
    outcome = "ready"
    try:
        await verify_readiness()
    except TimeoutError:
        outcome = "timeout"
        logger.warning("Readiness check timed out")
    except Exception:  # noqa: BLE001 - every dependency failure is unready
        outcome = "unready"
        logger.exception("Readiness check failed")
    finally:
        READINESS_CHECKS_TOTAL.labels(outcome).inc()
        READINESS_CHECK_DURATION_SECONDS.observe(time.perf_counter() - started_at)

    if outcome != "ready":
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy"},
        )
    return JSONResponse(content={"status": "ok"})
