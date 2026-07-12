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

    async def _fetch(self) -> JWKSCache:
        try:
            response = await self.client.get(self.settings.jwks_url, timeout=self.settings.fetch_timeout_seconds, follow_redirects=False)
            response.raise_for_status()
            if len(response.content) > _MAX_BODY:
                raise ValueError("body")
            payload = json.loads(response.content)
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
            _refresh.labels("failure").inc()
            raise _unavailable()
        cache = JWKSCache(keys, self.clock(), (self.cache.generation + 1) if self.cache else 1)
        self.cache = cache
        _refresh.labels("success").inc()
        _age.set(0)
        return cache

    async def signing_key(self, header: dict) -> jwt.PyJWK:
        if header.get("alg") != "RS256" or not _safe_text(header.get("kid")):
            raise _invalid()
        kid = header["kid"]
        now = self.clock()
        cache = self.cache
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
            if cache and now - cache.fetched_at < self.settings.cache_ttl_seconds and kid in cache.keys:
                _cache_use.labels("fresh").inc()
                return cache.keys[kid]
            try:
                cache = await self._fetch()
            except HTTPException:
                if self.cache and kid in self.cache.keys and now - self.cache.fetched_at <= self.settings.max_stale_seconds:
                    _cache_use.labels("stale").inc()
                    return self.cache.keys[kid]
                raise
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
    _client = httpx.AsyncClient(follow_redirects=False)
    _verifier = OIDCVerifier(settings, _client)

async def close_oidc_runtime() -> None:
    global _verifier, _client
    client, _client, _verifier = _client, None, None
    if client is not None:
        await client.aclose()

def get_oidc_verifier() -> OIDCVerifier:
    if _verifier is None: raise _unavailable()
    return _verifier
