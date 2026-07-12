"""Lifecycle-managed, bounded JWKS verifier."""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Callable

import httpx
import jwt
from fastapi import HTTPException, status
from prometheus_client import Counter, Gauge

from oidc_settings import OIDCVerifierSettings, load_oidc_verifier_settings

_MAX_BODY = 256 * 1024
_refresh = Counter("jwks_refresh_total", "JWKS refreshes.", ("outcome",))
_cache_use = Counter("jwks_cache_use_total", "JWKS cache use.", ("state",))
_unknown = Counter("jwks_unknown_kid_total", "Unknown JWKS key IDs.")
_age = Gauge("jwks_cache_age_seconds", "JWKS cache age.")


def _invalid(detail: str = "Invalid authentication token") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


def _unavailable() -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Authentication service unavailable")


def _safe_text(value: object, maximum: int = 256) -> bool:
    return isinstance(value, str) and bool(value) and len(value) <= maximum and all(char.isprintable() and not char.isspace() for char in value)


@dataclass(frozen=True, slots=True)
class JWKSCache:
    keys: dict[str, jwt.PyJWK]
    fetched_at: float
    generation: int


class OIDCVerifier:
    def __init__(self, settings: OIDCVerifierSettings, client: httpx.AsyncClient, clock: Callable[[], float] = time.monotonic):
        self.settings, self.client, self.clock = settings, client, clock
        self.cache: JWKSCache | None = None
        self.lock = asyncio.Lock()
        self.refresh_attempt_serial = 0
        self.last_refresh_outcome: str | None = None
        self.last_refresh_completed_at: float | None = None
        self.last_unknown_refresh_completed_at: float | None = None

    def _failure_retry_active(self, now: float) -> bool:
        return (
            self.last_refresh_outcome == "failure"
            and self.last_refresh_completed_at is not None
            and now - self.last_refresh_completed_at < self.settings.refresh_failure_retry_seconds
        )

    async def _fetch(self) -> JWKSCache:
        try:
            async with self.client.stream("GET", self.settings.jwks_url, timeout=self.settings.fetch_timeout_seconds, follow_redirects=False) as response:
                response.raise_for_status()
                length = response.headers.get("content-length")
                if length is not None and int(length) > _MAX_BODY:
                    raise ValueError("body")
                chunks = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                    if len(chunks) + len(chunk) > _MAX_BODY:
                        raise ValueError("body")
                    chunks.extend(chunk)
            payload = json.loads(bytes(chunks))
            values = payload.get("keys") if isinstance(payload, dict) else None
            if not isinstance(values, list) or not values:
                raise ValueError("keys")
            keys: dict[str, jwt.PyJWK] = {}
            for value in values:
                if not isinstance(value, dict) or not _safe_text(value.get("kid")):
                    raise ValueError("key")
                if value.get("kty") != "RSA" or value.get("use", "sig") != "sig" or value.get("alg", "RS256") != "RS256":
                    raise ValueError("key")
                kid = value["kid"]
                if kid in keys:
                    raise ValueError("duplicate")
                keys[kid] = jwt.PyJWK(value)
        except Exception:
            self.refresh_attempt_serial += 1
            self.last_refresh_outcome = "failure"
            self.last_refresh_completed_at = self.clock()
            _refresh.labels("failure").inc()
            raise _unavailable()
        cache = JWKSCache(keys, self.clock(), (self.cache.generation + 1) if self.cache else 1)
        self.cache = cache
        self.refresh_attempt_serial += 1
        self.last_refresh_outcome = "success"
        self.last_refresh_completed_at = cache.fetched_at
        _refresh.labels("success").inc()
        _age.set(0)
        return cache

    async def signing_key(self, header: dict) -> jwt.PyJWK:
        if header.get("alg") != "RS256" or not _safe_text(header.get("kid")):
            raise _invalid()
        kid = header["kid"]
        now = self.clock()
        cache = self.cache
        observed_generation = cache.generation if cache else 0
        observed_attempt = self.refresh_attempt_serial
        if cache:
            cache_age = now - cache.fetched_at
            _age.set(max(cache_age, 0))
            if cache_age < self.settings.cache_ttl_seconds and kid in cache.keys:
                _cache_use.labels("fresh").inc()
                return cache.keys[kid]
        unknown = not cache or kid not in cache.keys
        if unknown: _unknown.inc()
        async with self.lock:
            cache = self.cache
            now = self.clock()
            if self.refresh_attempt_serial != observed_attempt:
                if cache and kid in cache.keys and now - cache.fetched_at < self.settings.cache_ttl_seconds:
                    _cache_use.labels("fresh").inc()
                    return cache.keys[kid]
                if self.last_refresh_outcome == "success":
                    raise _invalid()
                if cache:
                    _age.set(max(now - cache.fetched_at, 0))
                    if kid in cache.keys and now - cache.fetched_at <= self.settings.max_stale_seconds:
                        _cache_use.labels("stale").inc()
                        return cache.keys[kid]
                raise _unavailable()
            if cache and cache.generation != observed_generation:
                if kid in cache.keys:
                    _cache_use.labels("fresh").inc()
                    return cache.keys[kid]
                raise _invalid()
            if cache and now - cache.fetched_at < self.settings.cache_ttl_seconds and kid in cache.keys:
                _cache_use.labels("fresh").inc()
                return cache.keys[kid]
            stale_key = cache.keys.get(kid) if cache else None
            if self._failure_retry_active(now):
                if stale_key is not None and cache is not None and now - cache.fetched_at <= self.settings.max_stale_seconds:
                    _cache_use.labels("stale").inc()
                    return stale_key
                raise _unavailable()
            if unknown and self.last_unknown_refresh_completed_at is not None and now - self.last_unknown_refresh_completed_at < self.settings.unknown_kid_refresh_cooldown_seconds:
                raise _invalid() if self.last_refresh_outcome == "success" else _unavailable()
            try:
                cache = await self._fetch()
            except HTTPException:
                now = self.clock()
                if self.cache:
                    _age.set(max(now - self.cache.fetched_at, 0))
                if self.cache and kid in self.cache.keys and now - self.cache.fetched_at <= self.settings.max_stale_seconds:
                    _cache_use.labels("stale").inc()
                    return self.cache.keys[kid]
                raise
            finally:
                if unknown:
                    self.last_unknown_refresh_completed_at = self.clock()
            if kid not in cache.keys:
                raise _invalid()
            return cache.keys[kid]


_verifier: OIDCVerifier | None = None
_client: httpx.AsyncClient | None = None

async def init_oidc_runtime() -> None:
    global _verifier, _client
    if _client is not None: return
    settings = load_oidc_verifier_settings()
    if settings is None: return
    client = httpx.AsyncClient(follow_redirects=False)
    try:
        verifier = OIDCVerifier(settings, client)
    except Exception:
        await client.aclose()
        raise
    _client, _verifier = client, verifier

async def close_oidc_runtime() -> None:
    global _verifier, _client
    client, _client, _verifier = _client, None, None
    if client is not None:
        await client.aclose()

def get_oidc_verifier() -> OIDCVerifier:
    if _verifier is None: raise _unavailable()
    return _verifier
