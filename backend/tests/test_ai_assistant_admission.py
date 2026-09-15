"""Owner-keyed admission bounds for AI run creation.

The review finding: one-active-run-per-conversation still allowed unlimited
conversations or browser tabs to create unlimited Docker sandboxes and billed
model runs. Two independent bounds close it, and these tests pin both:

* the public turn route carries the repository ``rate_limits.py`` dependency,
  keyed to the authenticated owner subject rather than to a conversation id;
* the runtime refuses a third simultaneous run for the same owner.

Neither bound polices an accepted run: no other AI route carries a rate-limit
policy, so tool calls and internal turns stay unlimited.
"""

from __future__ import annotations

import asyncio
import ipaddress
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute, iter_route_contexts

import rate_limits
from ai_assistant import settings as ai_settings
from auth import AuthClaims
from main import app as retail_app
from rate_limit_settings import PolicySettings, RateLimitSettings
from rate_limit_store import RateLimitDecision
from rate_limits import AI_TURN_LIMIT, RateLimitPolicy, rate_limit

OWNER = "owner-subject-1"
OTHER_OWNER = "owner-subject-2"
TURN_PATH = "/api/ai/conversations/{conversation_id}/turn"
UNLIMITED_AI_ROUTES = (
    ("POST", "/api/ai/conversations/{conversation_id}/steer"),
    ("POST", "/api/ai/conversations/{conversation_id}/stop"),
    ("GET", "/api/ai/conversations/{conversation_id}/messages"),
    ("GET", "/api/ai/artifacts/{artifact_id}/download"),
    ("POST", "/api/ai/conversations"),
)


class CountingStore:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.keys: list[str] = []
        self.lock = asyncio.Lock()

    async def check(self, key: str, limit: int, _window: int) -> RateLimitDecision:
        async with self.lock:
            self.keys.append(key)
            current = self.counts.get(key, 0)
            if current >= limit:
                return RateLimitDecision(False, 0, 7, 7)
            current += 1
            self.counts[key] = current
            return RateLimitDecision(True, limit - current, 0, 60)

    async def close(self) -> None:
        return None


def _limit_settings() -> RateLimitSettings:
    return RateLimitSettings(
        (ipaddress.ip_network("127.0.0.1/32"),),
        "none",
        "redis://localhost",
        "s" * 43,
        "closed",
        {"ai_turn": PolicySettings(AI_TURN_LIMIT.limit, AI_TURN_LIMIT.window_seconds)},
    )


def _claims(subject: str) -> AuthClaims:
    return AuthClaims(
        subject, "owner@example.invalid", "user", ["unihub-manager"], "issuer", "audience", 0, 0, {}
    )


def _ai_route(method: str, path: str) -> Any:
    for route in retail_app.routes:
        for context in iter_route_contexts([route]):
            original = context.original_route
            if (
                isinstance(original, APIRoute)
                and original.path == path
                and method in (original.methods or set())
            ):
                return original
    raise AssertionError(f"AI route not found: {method} {path}")


def _rate_limit_dependencies(route: APIRoute) -> set[str]:
    return {
        name
        for dependency in route.dependant.dependencies
        if (name := getattr(dependency.call, "__name__", "")).startswith("rate_limit_")
    }


def _admission_app(store: CountingStore) -> FastAPI:
    app = FastAPI()
    dependency = rate_limit(AI_TURN_LIMIT)

    @app.post("/turn", dependencies=[Depends(dependency)])
    async def turn() -> dict[str, bool]:
        return {"accepted": True}

    return app


def test_ai_run_start_policy_is_a_generous_owner_only_bound() -> None:
    assert AI_TURN_LIMIT == RateLimitPolicy("ai_turn", 10, 60)
    # Registered in the shared policy table so production can tune it without
    # touching router code.
    from rate_limit_settings import _POLICY_DEFAULTS

    assert _POLICY_DEFAULTS["ai_turn"] == ("RATE_LIMIT_AI_TURN", 10, 60)


def test_only_the_run_start_route_is_admission_bounded() -> None:
    assert _rate_limit_dependencies(_ai_route("POST", TURN_PATH)) == {"rate_limit_ai_turn"}
    for method, path in UNLIMITED_AI_ROUTES:
        assert _rate_limit_dependencies(_ai_route(method, path)) == set(), path


@pytest.mark.anyio
async def test_run_start_burst_is_rejected_after_the_owner_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = CountingStore()
    monkeypatch.setattr(rate_limits, "_store", store)
    monkeypatch.setattr(rate_limits, "_settings", _limit_settings())
    app = _admission_app(store)
    app.dependency_overrides[rate_limits.require_auth] = lambda: _claims(OWNER)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        statuses = [(await client.post("/turn")).status_code for _ in range(11)]
        rejected = await client.post("/turn")

    assert statuses[:10] == [200] * 10
    assert statuses[10] == rejected.status_code == 429
    assert rejected.headers["retry-after"] == "7"
    # Retries across newly created conversations cannot open a second budget.
    assert len(store.counts) == 1


@pytest.mark.anyio
async def test_admission_is_keyed_to_the_owner_not_the_conversation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = CountingStore()
    monkeypatch.setattr(rate_limits, "_store", store)
    monkeypatch.setattr(rate_limits, "_settings", _limit_settings())
    app = _admission_app(store)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for subject in (OWNER, OWNER, OTHER_OWNER):
            app.dependency_overrides[rate_limits.require_auth] = (
                lambda subject=subject: _claims(subject)
            )
            response = await client.post("/turn", params={"conversation_id": subject})
            assert response.status_code == 200

    assert store.keys[0] == store.keys[1]
    assert store.keys[2] != store.keys[0]
    assert not any(OWNER in key for key in store.keys)


@pytest.mark.parametrize(("raw", "expected"), [("1", 1), ("2", 2), ("16", 16)])
def test_owner_run_ceiling_is_configurable_within_bounds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, raw: str, expected: int
) -> None:
    _base_ai_env(monkeypatch, tmp_path)
    monkeypatch.setenv(ai_settings.AI_MAX_CONCURRENT_RUNS_ENV, raw)

    assert ai_settings.load_ai_assistant_settings().max_concurrent_runs_per_owner == expected


def test_owner_run_ceiling_default_is_two_and_rejects_out_of_range(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _base_ai_env(monkeypatch, tmp_path)
    monkeypatch.delenv(ai_settings.AI_MAX_CONCURRENT_RUNS_ENV, raising=False)
    assert ai_settings.load_ai_assistant_settings().max_concurrent_runs_per_owner == 2

    for invalid in ("0", "17", "two", ""):
        monkeypatch.setenv(ai_settings.AI_MAX_CONCURRENT_RUNS_ENV, invalid)
        with pytest.raises(RuntimeError):
            ai_settings.load_ai_assistant_settings()


def _base_ai_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("UNIHUB_ENV", "development")
    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("AI_ASSISTANT_SNAPSHOT_ROOT", str(tmp_path / "snapshots"))
