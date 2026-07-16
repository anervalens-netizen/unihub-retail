from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from auth import AuthClaims
from models import (
    StoreActivityChangeRequest,
    StoreActivityChangeResponse,
)
from routers.stores import change_store_activity


def claims() -> AuthClaims:
    return AuthClaims(
        sub="stable-synthetic-subject",
        email="mutable@example.invalid",
        preferred_username="synthetic-user",
        groups=["unihub-admin"],
        iss="https://issuer.invalid",
        aud="synthetic-audience",
        iat=1,
        exp=2,
        raw={},
    )


@pytest.mark.asyncio
async def test_activity_endpoint_persists_subject_not_email() -> None:
    expected = StoreActivityChangeResponse(
        site_code="SYNTHETIC-SITE",
        previous_is_active=True,
        is_active=False,
        event_id=9,
    )
    service = AsyncMock()
    service.change_activity.return_value = expected

    result = await change_store_activity(
        site_code=" SYNTHETIC-SITE ",
        payload=StoreActivityChangeRequest(
            is_active=False,
            expected_is_active=True,
            reason="Synthetic approved closure",
        ),
        claims=claims(),
        _rate_limit=None,
        svc=service,
    )

    assert result == expected
    service.change_activity.assert_awaited_once_with(
        site_code="SYNTHETIC-SITE",
        expected_is_active=True,
        new_is_active=False,
        reason="Synthetic approved closure",
        requested_by_sub="stable-synthetic-subject",
    )


def test_activity_reason_rejects_whitespace_only_approval() -> None:
    with pytest.raises(ValidationError):
        StoreActivityChangeRequest(
            is_active=False,
            expected_is_active=True,
            reason="              ",
        )
