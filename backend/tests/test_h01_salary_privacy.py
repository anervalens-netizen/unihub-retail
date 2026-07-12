from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[2]


def test_public_salary_surface_has_no_raw_identity_terms() -> None:
    paths = [
        ROOT / "src/api/salarii.ts",
        ROOT / "src/components/SalariiSubtab.tsx",
        ROOT / "src/components/SalaryDrawer.tsx",
        ROOT / "backend/routers/salarii.py",
    ]
    forbidden = ("cnp", "salary_cnp", "maskCnp", "/agents/history/")
    for path in paths:
        source = path.read_text(encoding="utf-8").lower()
        assert not any(term.lower() in source for term in forbidden), path


def test_public_response_keys_are_opaque() -> None:
    source = (ROOT / "backend/services/salarii.py").read_text(encoding="utf-8")
    assert '"person_id"' in source
    assert '"salary_cnp"' not in source


def test_runtime_salary_repository_cannot_query_private_identity_columns() -> None:
    source = (ROOT / "backend/repositories/salarii.py").read_text(encoding="utf-8").lower()
    assert "cnp" not in source
    assert "salary_private" not in source
    assert "salary_cnp" not in source


@pytest.mark.asyncio
async def test_identity_dependency_fails_closed_but_base_service_is_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    from routers import salarii

    monkeypatch.delenv("SALARY_PERSON_ID_HMAC_KEY", raising=False)
    monkeypatch.setattr(salarii, "get_pool", AsyncMock(return_value=object()))
    assert (await salarii.get_salarii_service()).person_id_key is None
    with pytest.raises(HTTPException) as exc_info:
        await salarii.get_identity_salarii_service()
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "salary identity is unavailable"
