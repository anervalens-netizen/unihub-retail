"""Read-only API smoke test for the Authentik-protected Retail backend."""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
from pathlib import Path
from typing import Any

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from domain.http_endpoints import validated_http_endpoint


BASE_URL = os.getenv("UNIHUB_API_URL", "http://localhost:8000").rstrip("/")
TOKEN = os.getenv("UNIHUB_SMOKE_TOKEN", "").strip()


def request_json(path: str, token: str | None = None) -> Any:
    url = f"{BASE_URL}{path}"
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    endpoint = validated_http_endpoint(url, setting="UNIHUB_API_URL")
    response = httpx.get(
        endpoint,
        headers=headers,
        timeout=30,
        follow_redirects=False,
    )
    response.raise_for_status()
    return response.json()


def main() -> int:
    try:
        health = request_json("/health")
        result: dict[str, object] = {
            "base_url": BASE_URL,
            "health": health,
        }

        if not TOKEN:
            result["protected_checks"] = (
                "skipped: set UNIHUB_SMOKE_TOKEN to an Authentik access token"
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        months = request_json("/api/filters/months", TOKEN)
        if not isinstance(months, list) or not months:
            raise RuntimeError("Nu exista luni completed disponibile")

        month = str(months[0])
        query = urllib.parse.urlencode({"month": month})
        summary = request_json(f"/api/dashboard/summary?{query}", TOKEN)
        filters = request_json(f"/api/filters/options?{query}", TOKEN)
        stores = request_json("/api/stores", TOKEN)

        result.update(
            {
                "latest_month": month,
                "summary": {
                    "total_sales": summary.get("total_sales"),
                    "total_stores": summary.get("total_stores"),
                    "total_agents": summary.get("total_agents"),
                },
                "filter_counts": {
                    "firme": len(filters.get("firme", [])),
                    "magazine": len(filters.get("magazine", [])),
                    "agenti": len(filters.get("agenti", [])),
                },
                "stores_count": len(stores),
                "mode": "read-only",
            }
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP error {exc.code}: {error_body}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"Smoke test failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
