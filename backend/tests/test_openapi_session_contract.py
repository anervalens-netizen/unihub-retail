from __future__ import annotations

from main import app


def test_session_endpoints_publish_typed_response_contracts() -> None:
    schema = app.openapi()

    session_response = schema["paths"]["/auth/session"]["get"]["responses"]["200"]
    logout_response = schema["paths"]["/auth/session/logout"]["post"]["responses"]["200"]

    assert session_response["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/SessionStatusResponse"
    }
    assert logout_response["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/SessionLogoutResponse"
    }

    session_model = schema["components"]["schemas"]["SessionStatusResponse"]
    assert session_model["required"] == ["profile", "csrf_token"]
    assert session_model["properties"]["profile"] == {
        "$ref": "#/components/schemas/SessionProfileResponse"
    }

