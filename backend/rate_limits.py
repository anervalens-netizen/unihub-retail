"""Trusted-identity, distributed and fail-closed request rate limiting."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, Response, status
from prometheus_client import Counter, Histogram
from redis.asyncio import Redis

from auth import AuthClaims, require_auth
from client_ip import resolve_client_ip
from rate_limit_settings import PolicySettings, RateLimitSettings, load_rate_limit_settings
from rate_limit_store import RateLimitDecision, RateLimitStore, ValkeyRateLimitStore


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    name: str
    limit: int
    window_seconds: int


AUTH_PROXY_LIMIT = RateLimitPolicy("auth_proxy", 120, 60)
SALES_IMPORT_UPLOAD_LIMIT = RateLimitPolicy("sales_import_upload", 5, 900)
REPORT_EXPORT_LIMIT = RateLimitPolicy("report_export", 30, 60)
BUSINESS_WRITE_LIMIT = RateLimitPolicy("business_write", 60, 60)
GRILE_JOB_LIMIT = RateLimitPolicy("grile_job", 10, 300)
TARGET_MUTATION_LIMIT = RateLimitPolicy("target_mutation", 30, 300)


_decisions = Counter(
    "rate_limit_decisions_total",
    "Distributed rate-limit decisions.",
    ("policy", "outcome"),
)
_duration = Histogram(
    "rate_limit_backend_duration_seconds",
    "Distributed rate-limit backend latency.",
    ("operation",),
)
_ip_resolution = Counter(
    "rate_limit_client_ip_resolution_total",
    "Trusted client IP resolution outcomes.",
    ("mode", "outcome"),
)


_settings: RateLimitSettings | None = None
_store: RateLimitStore | None = None


def _unavailable() -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Rate limit service unavailable")


def _policy(policy: RateLimitPolicy, settings: RateLimitSettings) -> PolicySettings:
    return settings.policies.get(policy.name, PolicySettings(policy.limit, policy.window_seconds))


def _identity_key(request: Request, claims: AuthClaims | None, settings: RateLimitSettings) -> str:
    if claims is not None:
        namespace, identity = "user", claims.sub
    else:
        resolution = resolve_client_ip(request, settings)
        _ip_resolution.labels(resolution.mode, resolution.outcome).inc()
        namespace, identity = "ip", resolution.address
    digest = hmac.new(
        settings.key_hmac_secret.encode("utf-8"),
        f"{namespace}:{identity}".encode("utf-8", "surrogateescape"),
        hashlib.sha256,
    ).hexdigest()
    return f"unihub:retail:ratelimit:v1:{{policy}}:{digest}"


def _headers(policy: PolicySettings, decision: RateLimitDecision) -> dict[str, str]:
    return {
        "RateLimit-Limit": str(policy.limit),
        "RateLimit-Remaining": str(decision.remaining),
        "RateLimit-Reset": str(decision.reset_after_seconds),
    }


async def enforce_rate_limit(
    request: Request,
    policy: RateLimitPolicy,
    claims: AuthClaims | None = None,
    store: RateLimitStore | None = None,
    settings: RateLimitSettings | None = None,
    response: Response | None = None,
) -> RateLimitDecision:
    active_store = store or _store
    active_settings = settings or _settings
    if active_store is None or active_settings is None:
        _decisions.labels(policy.name, "error").inc()
        raise _unavailable()
    configured_policy = _policy(policy, active_settings)
    key = _identity_key(request, claims, active_settings).format(policy=policy.name)
    try:
        with _duration.labels("eval").time():
            decision = await active_store.check(key, configured_policy.limit, configured_policy.window_seconds)
    except asyncio.CancelledError:
        raise
    except Exception:
        _decisions.labels(policy.name, "error").inc()
        raise _unavailable()
    headers = _headers(configured_policy, decision)
    if not decision.allowed:
        _decisions.labels(policy.name, "rejected").inc()
        headers["Retry-After"] = str(max(1, decision.retry_after_seconds))
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Prea multe cereri. Reincercati mai tarziu.",
            headers=headers,
        )
    _decisions.labels(policy.name, "allowed").inc()
    if response is not None:
        for name, value in headers.items():
            response.headers[name] = value
    return decision


def rate_limit(policy: RateLimitPolicy):
    async def dependency(
        request: Request,
        response: Response,
        claims: AuthClaims = Depends(require_auth),
    ) -> None:
        await enforce_rate_limit(request, policy, claims, response=response)

    dependency.__name__ = f"rate_limit_{policy.name}"
    return dependency


def anonymous_rate_limit(policy: RateLimitPolicy):
    async def dependency(request: Request, response: Response) -> None:
        await enforce_rate_limit(request, policy, response=response)

    dependency.__name__ = f"rate_limit_{policy.name}"
    return dependency


async def init_rate_limit_runtime() -> None:
    global _settings, _store
    if _store is not None:
        return
    settings = load_rate_limit_settings()
    if settings is None:
        return
    client = Redis.from_url(
        settings.valkey_url,
        decode_responses=True,
        socket_connect_timeout=1.0,
        socket_timeout=1.0,
    )
    store = ValkeyRateLimitStore(client)
    try:
        await asyncio.wait_for(client.ping(), timeout=1.0)
    except Exception:
        await store.close()
        raise RuntimeError("Distributed rate limit backend unavailable")
    _settings, _store = settings, store


async def close_rate_limit_runtime() -> None:
    global _settings, _store
    store, _settings, _store = _store, None, None
    if store is not None:
        await store.close()
