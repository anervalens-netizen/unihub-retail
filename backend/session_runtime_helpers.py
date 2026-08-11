from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from typing import Any

from auth import AuthClaims


async def drain_tasks(
    tasks: Iterable[asyncio.Task[Any]],
    *,
    timeout: float,
) -> int:
    active = tuple(tasks)
    if not active:
        return 0
    _done, pending = await asyncio.wait(active, timeout=timeout)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    return len(pending)


def oidc_identity_is_continuous(expected: Any, actual: Any) -> bool:
    if isinstance(expected, Mapping):
        expected_sub, expected_iss = expected.get("sub"), expected.get("iss")
    else:
        expected_sub = getattr(expected, "sub", None)
        expected_iss = getattr(expected, "iss", None)
    return (
        isinstance(expected_sub, str)
        and isinstance(expected_iss, str)
        and expected_sub == getattr(actual, "sub", None)
        and expected_iss == getattr(actual, "iss", None)
    )


def auth_claims_from_record(payload: dict[str, Any]) -> AuthClaims:
    return AuthClaims(
        sub=str(payload["sub"]),
        email=str(payload.get("email", "")),
        preferred_username=str(payload.get("preferred_username", "")),
        groups=[str(group) for group in payload.get("groups", [])],
        iss=str(payload["iss"]),
        aud=str(payload["aud"]),
        iat=int(payload["iat"]),
        exp=int(payload["exp"]),
        raw={},
    )
