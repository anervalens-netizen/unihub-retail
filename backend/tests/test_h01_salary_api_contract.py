from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from typing import cast
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.exceptions import ResponseValidationError

from auth import AuthClaims, require_auth
from repositories.salarii import SalariiRepository
from routers.salarii import get_identity_salarii_service, get_salarii_service
from schemas.salarii import SalaryAgentsSummaryResponse, SalaryHistoryResponse, SalaryRecordPublic
from services.salarii import SalariiService
from salary_identity import make_salary_person_id


PERSON_ID_KEY = "synthetic-hmac-key-for-tests-abcdefghijklmnopqrstuvwxyz"
PERSON_ID = make_salary_person_id("synthetic-private-id-a", "Salary Test Agent", PERSON_ID_KEY)


class _FakeSalaryRepo:
    def __init__(self) -> None:
        self.fetch_agents_summary = AsyncMock(return_value={
            "items": [{
                "person_id": PERSON_ID,
                "full_name": "Salary Test Agent",
                "company_name": "Mobicell",
                "locatie": "Test Store",
                "month_count": 1,
                "avg_month_count": 1,
                "total_salary": Decimal("3000"),
                "avg_salary": Decimal("3000"),
                "cnp": "synthetic-private-id-a",
                "agent_key": "cnp:synthetic-private-id-a",
            }],
            "total": 1,
        })
        self.fetch_agent_history_by_person_id = AsyncMock(return_value=[{
            "year": 2097, "month": 1, "company_name": "Mobicell",
            "total_salary": Decimal("3000"), "site_code": "H01API", "locatie": "Test Store",
            "cnp": "synthetic-private-id-a",
        }])
        self.fetch_records = AsyncMock(return_value=[{
            "id": 1, "year": 2097, "month": 1, "full_name": "Salary Test Agent",
            "person_id": PERSON_ID, "total_salary": Decimal("3000"), "company_name": "Mobicell",
            "site_code": "H01API", "locatie": "Test Store", "cnp": "synthetic-private-id-a",
        }])
        self.fetch_agent_salary_link = AsyncMock(return_value={
            "agent_code": "API1", "site_code": "H01API", "salary_full_name": "",
            "salary_cnp": "synthetic-private-id-a", "person_id": PERSON_ID,
            "match_status": "confirmed", "match_source": "manual", "confidence": "high",
            "effective_from_month": None, "note": None,
        })
        self.fetch_agent_history_by_salary_link = AsyncMock(return_value=[{
            "year": 2097, "month": 1, "company_name": "Mobicell",
            "total_salary": Decimal("3000"), "site_code": "H01API", "locatie": "Test Store",
        }])


def _salary_claims() -> AuthClaims:
    return AuthClaims(
        sub="test-user", email="test@example.invalid", preferred_username="test-user",
        groups=["unihub-hr"], iss="test", aud="test", iat=0, exp=1, raw={},
    )


@contextmanager
def _salary_app_overrides(service: SalariiService | object | None, base_service: object | None = None):
    from main import app

    old_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[require_auth] = _salary_claims
    if service is not None:
        app.dependency_overrides[get_identity_salarii_service] = lambda: service
    if base_service is not None:
        app.dependency_overrides[get_salarii_service] = lambda: base_service
    try:
        yield app
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(old_overrides)


@pytest.mark.anyio
async def test_asgi_identity_endpoints_emit_only_public_contract_fields() -> None:
    service = SalariiService(cast(SalariiRepository, _FakeSalaryRepo()), PERSON_ID_KEY)
    with _salary_app_overrides(service) as app:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            summary = await client.get("/salarii/agents/summary")
            history = await client.get(f"/salarii/agents/{PERSON_ID}/history")
            records = await client.get("/salarii/records")
            retail_link = await client.get(
                "/salarii/agents/history-by-retail-code",
                params={"agent_code": "API1", "site_code": "H01API"},
            )

    assert summary.status_code == history.status_code == records.status_code == retail_link.status_code == 200
    payloads = [summary.json(), history.json(), records.json(), retail_link.json()]
    assert "cnp" not in str(payloads)
    assert "salary_cnp" not in str(payloads)
    assert set(summary.json()["items"][0]) == {
        "person_id", "full_name", "company_name", "locatie", "month_count",
        "avg_month_count", "total_salary", "avg_salary",
    }
    assert set(history.json()["records"][0]) == {
        "year", "month", "company_name", "total_salary", "site_code", "locatie",
    }
    assert set(records.json()[0]) == {
        "id", "year", "month", "full_name", "person_id", "total_salary",
        "company_name", "site_code", "locatie",
    }
    assert summary.json()["items"][0]["person_id"] == PERSON_ID
    assert summary.json()["total"] == 1
    assert retail_link.json()["link"]["person_id"] == PERSON_ID
    assert len(retail_link.json()["records"]) == 1


@pytest.mark.anyio
async def test_asgi_history_handles_unknown_and_malformed_person_ids() -> None:
    repo = _FakeSalaryRepo()
    repo.fetch_agent_history_by_person_id.return_value = []
    with _salary_app_overrides(SalariiService(cast(SalariiRepository, repo), PERSON_ID_KEY)) as app:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            unknown = await client.get(f"/salarii/agents/{PERSON_ID}/history")
            malformed = await client.get("/salarii/agents/not-an-opaque-id/history")

    assert unknown.status_code == 404
    assert unknown.json() == {"detail": "salary agent not found"}
    assert malformed.status_code == 422


@pytest.mark.anyio
async def test_asgi_unknown_retail_link_hides_identity_and_skips_history() -> None:
    repo = _FakeSalaryRepo()
    repo.fetch_agent_salary_link.return_value = {
        "agent_code": "API2", "site_code": "H01API", "salary_full_name": None,
        "salary_cnp": None, "person_id": None, "match_status": "unknown",
        "match_source": "manual", "confidence": "unknown", "effective_from_month": None, "note": None,
    }
    with _salary_app_overrides(SalariiService(cast(SalariiRepository, repo), PERSON_ID_KEY)) as app:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get(
                "/salarii/agents/history-by-retail-code",
                params={"agent_code": "API2", "site_code": "H01API"},
            )

    assert response.status_code == 200
    assert response.json()["link"]["person_id"] is None
    assert response.json()["records"] == []
    assert response.json()["total"] == response.json()["avg"] == "0.00"
    repo.fetch_agent_history_by_salary_link.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("key", [None, ""])
async def test_asgi_identity_endpoint_returns_generic_503_without_key(monkeypatch: pytest.MonkeyPatch, key: str | None) -> None:
    if key is None:
        monkeypatch.delenv("SALARY_PERSON_ID_HMAC_KEY", raising=False)
    else:
        monkeypatch.setenv("SALARY_PERSON_ID_HMAC_KEY", key)

    class _BaseService:
        async def get_overview(self, *args, **kwargs):
            return {"total": 1}

    with _salary_app_overrides(None, _BaseService()) as app:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/salarii/agents/summary")
            overview = await client.get("/salarii/overview")

    assert response.status_code == 503
    assert response.json() == {"detail": "salary identity is unavailable"}
    assert overview.status_code == 200
    assert overview.json() == {"total": "1"}


@pytest.mark.anyio
async def test_salary_money_is_serialized_exactly_without_binary_float_drift() -> None:
    repo = _FakeSalaryRepo()
    repo.fetch_agent_history_by_person_id.return_value = [
        {
            "year": 2026,
            "month": 1,
            "company_name": "Synthetic",
            "total_salary": Decimal("0.10"),
            "site_code": None,
            "locatie": None,
        },
        {
            "year": 2026,
            "month": 1,
            "company_name": "Synthetic",
            "total_salary": Decimal("0.20"),
            "site_code": None,
            "locatie": None,
        },
    ]
    with _salary_app_overrides(
        SalariiService(cast(SalariiRepository, repo), PERSON_ID_KEY)
    ) as app:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.get(f"/salarii/agents/{PERSON_ID}/history")

    assert response.status_code == 200
    assert response.json()["total"] == "0.30"
    assert [row["total_salary"] for row in response.json()["records"]] == [
        "0.10",
        "0.20",
    ]


@pytest.mark.anyio
async def test_repeated_site_query_params_preserve_values_containing_commas() -> None:
    class _CapturingService:
        def __init__(self) -> None:
            self.site_code: list[str] | None = None

        async def get_overview(self, company_name, site_code, regional, asm):
            self.site_code = site_code
            return {"total": Decimal("0.00")}

    service = _CapturingService()
    with _salary_app_overrides(None, service) as app:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.get(
                "/salarii/overview",
                params=[("site_code", "STORE, ONE"), ("site_code", "STORE TWO")],
            )

    assert response.status_code == 200
    assert service.site_code == ["STORE, ONE", "STORE TWO"]


@pytest.mark.anyio
async def test_asgi_response_model_rejects_unapproved_internal_field() -> None:
    class _LeakyService:
        async def get_agents_summary(self, *args, **kwargs):
            return {
                "items": [{
                    "person_id": PERSON_ID, "full_name": "Salary Test Agent",
                    "company_name": "Mobicell", "locatie": None, "month_count": 1,
                    "avg_month_count": 1, "total_salary": 3000, "avg_salary": 3000,
                    "cnp": "synthetic-private-id-a",
                }],
                "total": 1,
            }

    with _salary_app_overrides(_LeakyService()) as app:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            with pytest.raises(ResponseValidationError):
                await client.get("/salarii/agents/summary")


def test_salary_public_models_forbid_internal_fields() -> None:
    public_models = (SalaryAgentsSummaryResponse, SalaryHistoryResponse, SalaryRecordPublic)
    for model in public_models:
        assert model.model_config.get("extra") == "forbid"
        assert "cnp" not in model.model_json_schema()


def test_openapi_uses_strict_salary_contracts() -> None:
    from main import app

    schema = app.openapi()
    paths = schema["paths"]
    assert "/salarii/agents/{person_id}/history" in paths
    assert "/salarii/agents/history/{cnp}" not in paths
    for path in (
        "/salarii/agents/summary",
        "/salarii/agents/{person_id}/history",
        "/salarii/agents/history-by-retail-code",
        "/salarii/records",
    ):
        assert "responses" in paths[path]["get"]
    public_openapi = str({key: value for key, value in schema["components"]["schemas"].items() if "Salary" in key})
    assert "salary_cnp" not in public_openapi
    assert "agent_key" not in public_openapi
