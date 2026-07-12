from __future__ import annotations

from schemas.salarii import SalaryAgentsSummaryResponse, SalaryHistoryResponse, SalaryRecordPublic


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
