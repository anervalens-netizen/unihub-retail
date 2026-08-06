"""OpenAPI must expose the explicit Target errors handled by the UI."""
from __future__ import annotations

from main import app


def test_target_mutations_publish_real_error_statuses() -> None:
    schema = app.openapi()
    paths = schema["paths"]

    assert set(paths["/api/target-calculator/scenarios/calculate"]["post"]["responses"]) >= {"200", "400", "409", "422"}
    assert set(paths["/api/target-calculator/scenarios/{scenario_id}/rows"]["patch"]["responses"]) >= {"200", "400", "404", "409", "422"}
    assert set(paths["/api/target-calculator/scenarios/{scenario_id}/finalize"]["post"]["responses"]) >= {"200", "400", "404", "409", "422"}


def test_target_read_routes_publish_not_found_and_conflict_metadata() -> None:
    schema = app.openapi()
    paths = schema["paths"]

    assert set(paths["/api/target-calculator/context"]["get"]["responses"]) >= {"200", "404"}
    assert set(paths["/api/target-calculator/scenarios/{scenario_id}"]["get"]["responses"]) >= {"200", "404", "409", "422"}
    assert set(paths["/api/target-calculator/scenarios/{scenario_id}/stores/{site_code}"]["get"]["responses"]) >= {"200", "404", "422"}
    assert set(paths["/api/target-calculator/scenarios/{scenario_id}/export"]["get"]["responses"]) >= {"200", "404", "409", "422"}
