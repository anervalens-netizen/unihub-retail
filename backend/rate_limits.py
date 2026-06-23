from __future__ import annotations

import math
import os
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable

from fastapi import Depends, HTTPException, Request, status

from auth import AuthClaims, require_auth


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    name: str
    limit: int
    window_seconds: int


AUTH_PROXY_LIMIT = RateLimitPolicy(
    name="auth_proxy",
    limit=_env_int("RATE_LIMIT_AUTH_PROXY", 120),
    window_seconds=_env_int("RATE_LIMIT_AUTH_PROXY_WINDOW_SECONDS", 60),
)
SALES_IMPORT_UPLOAD_LIMIT = RateLimitPolicy(
    name="sales_import_upload",
    limit=_env_int("RATE_LIMIT_SALES_IMPORT_UPLOAD", 5),
    window_seconds=_env_int("RATE_LIMIT_SALES_IMPORT_UPLOAD_WINDOW_SECONDS", 900),
)
REPORT_EXPORT_LIMIT = RateLimitPolicy(
    name="report_export",
    limit=_env_int("RATE_LIMIT_REPORT_EXPORT", 30),
    window_seconds=_env_int("RATE_LIMIT_REPORT_EXPORT_WINDOW_SECONDS", 60),
)
BUSINESS_WRITE_LIMIT = RateLimitPolicy(
    name="business_write",
    limit=_env_int("RATE_LIMIT_BUSINESS_WRITE", 60),
    window_seconds=_env_int("RATE_LIMIT_BUSINESS_WRITE_WINDOW_SECONDS", 60),
)
GRILE_JOB_LIMIT = RateLimitPolicy(
    name="grile_job",
    limit=_env_int("RATE_LIMIT_GRILE_JOB", 10),
    window_seconds=_env_int("RATE_LIMIT_GRILE_JOB_WINDOW_SECONDS", 300),
)
TARGET_MUTATION_LIMIT = RateLimitPolicy(
    name="target_mutation",
    limit=_env_int("RATE_LIMIT_TARGET_MUTATION", 30),
    window_seconds=_env_int("RATE_LIMIT_TARGET_MUTATION_WINDOW_SECONDS", 300),
)


class InMemoryRateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[tuple[str, str], deque[float]] = {}

    def reset(self) -> None:
        self._hits.clear()

    def hit(self, policy: RateLimitPolicy, key: str) -> int | None:
        now = self._clock()
        bucket_key = (policy.name, key)
        bucket = self._hits.setdefault(bucket_key, deque())
        cutoff = now - policy.window_seconds
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

        if len(bucket) >= policy.limit:
            retry_after = policy.window_seconds - (now - bucket[0])
            return max(1, math.ceil(retry_after))

        bucket.append(now)
        return None


rate_limiter = InMemoryRateLimiter()


def _client_ip(request: Request) -> str:
    cf_ip = request.headers.get("cf-connecting-ip", "").strip()
    if cf_ip:
        return cf_ip

    forwarded_for = request.headers.get("x-forwarded-for", "").strip()
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()

    if request.client:
        return request.client.host
    return "unknown"


def _rate_limit_key(request: Request, claims: AuthClaims | None) -> str:
    ip = _client_ip(request)
    if claims is None:
        return f"ip:{ip}"
    subject = claims.sub or claims.email or "unknown"
    return f"user:{subject}|ip:{ip}"


async def enforce_rate_limit(
    request: Request,
    policy: RateLimitPolicy,
    claims: AuthClaims | None = None,
    limiter: InMemoryRateLimiter = rate_limiter,
) -> None:
    retry_after = limiter.hit(policy, _rate_limit_key(request, claims))
    if retry_after is None:
        return

    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Prea multe cereri. Reincercati mai tarziu.",
        headers={"Retry-After": str(retry_after)},
    )


def rate_limit(policy: RateLimitPolicy):
    async def dependency(
        request: Request,
        claims: AuthClaims = Depends(require_auth),
    ) -> None:
        await enforce_rate_limit(request, policy, claims)

    dependency.__name__ = f"rate_limit_{policy.name}"
    return dependency


def anonymous_rate_limit(policy: RateLimitPolicy):
    async def dependency(request: Request) -> None:
        await enforce_rate_limit(request, policy)

    dependency.__name__ = f"rate_limit_{policy.name}"
    return dependency
