"""Bounded HTTP client for the external TimesFM forecast service."""
from __future__ import annotations

from typing import Any

import httpx

from domain.http_endpoints import validated_http_endpoint


class ForecastTimeoutError(RuntimeError):
    """The only transport failure eligible for explicit seasonal fallback."""


def post_forecast(
    api_url: str,
    api_key: str,
    payload: dict[str, Any],
    timeout: int,
) -> dict[str, Any]:
    endpoint = validated_http_endpoint(api_url, setting="TIMESFM_API_URL")
    try:
        response = httpx.post(
            endpoint,
            json=payload,
            headers={"Content-Type": "application/json", "X-API-Key": api_key},
            timeout=timeout,
            follow_redirects=False,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"TimesFM HTTP {exc.response.status_code}: {exc.response.text}"
        ) from exc
    except httpx.TimeoutException as exc:
        raise ForecastTimeoutError("TimesFM API request timed out") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"TimesFM API request failed: {exc}") from exc
