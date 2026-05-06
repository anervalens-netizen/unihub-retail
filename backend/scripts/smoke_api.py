# mypy: ignore-errors

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime


BASE_URL = os.getenv("UNIHUB_API_URL", "http://localhost:8000")
USERNAME = os.getenv("UNIHUB_SMOKE_USER", "admin")
PASSWORD = os.getenv("UNIHUB_SMOKE_PASSWORD", "9999")


def request_json(
    method: str,
    path: str,
    body: dict | None = None,
    token: str | None = None,
) -> object:
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url=url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def request_delete(path: str, token: str) -> object:
    return request_json("DELETE", path, token=token)


def main() -> int:
    try:
        health = request_json("GET", "/health")
        login = request_json(
            "POST",
            "/api/auth/login",
            body={"username": USERNAME, "password": PASSWORD},
        )
        token = str(login["access_token"])
        me = request_json("GET", "/api/auth/me", token=token)
        months = request_json("GET", "/api/filters/months", token=token)
        if not months:
            raise RuntimeError("Nu exista luni disponibile dupa seed")

        month = months[0]
        summary = request_json(
            "GET",
            f"/api/dashboard/summary?{urllib.parse.urlencode({'month': month})}",
            token=token,
        )
        filters = request_json(
            "GET",
            f"/api/filters/options?{urllib.parse.urlencode({'month': month})}",
            token=token,
        )
        stores = request_json("GET", "/api/stores", token=token)
        visits_before = request_json(
            "GET",
            f"/api/visits?{urllib.parse.urlencode({'month': month})}",
            token=token,
        )

        if not stores:
            raise RuntimeError("Lista de magazine este goala")

        store = stores[0]
        now = datetime.now(UTC)
        visit_id = f"smoke-{now.strftime('%Y%m%d%H%M%S')}"
        visit_payload = {
            "id": visit_id,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "data_raport": now.date().isoformat(),
            "ora_trimitere": "10:00:00",
            "firma": store["firma"],
            "regional": store["regional"],
            "asm": store["asm"],
            "magazin": store["locatie"],
            "site_code": store["site_code"],
            "durata_vizita_ore": 1,
            "curatenie": True,
            "imagine": True,
            "uniforma": True,
            "afise": False,
            "produse_promo": False,
            "status": "submitted",
            "completion_pct": 75,
            "source": "smoke-test",
            "notes": "API smoke test",
        }

        created_visit = request_json("POST", "/api/visits", body=visit_payload, token=token)
        visits_after_create = request_json(
            "GET",
            f"/api/visits?{urllib.parse.urlencode({'month': month, 'site_code': store['site_code']})}",
            token=token,
        )
        if not any(visit["id"] == visit_id for visit in visits_after_create):
            raise RuntimeError("Vizita creata nu a fost returnata de API")

        delete_result = request_delete(f"/api/visits/{visit_id}", token=token)
        visits_after_delete = request_json(
            "GET",
            f"/api/visits?{urllib.parse.urlencode({'month': month, 'site_code': store['site_code']})}",
            token=token,
        )
        if any(visit["id"] == visit_id for visit in visits_after_delete):
            raise RuntimeError("Vizita stearsa este inca prezenta in API")

        print(
            json.dumps(
                {
                    "health": health,
                    "login_role": login["role"],
                    "me": {"username": me["username"], "role": me["role"]},
                    "latest_month": month,
                    "summary": {
                        "total_sales": summary["total_sales"],
                        "total_stores": summary["total_stores"],
                        "total_agents": summary["total_agents"],
                    },
                    "filter_counts": {
                        "firme": len(filters["firme"]),
                        "magazine": len(filters["magazine"]),
                        "agenti": len(filters["agenti"]),
                    },
                    "stores_count": len(stores),
                    "visits_before": len(visits_before),
                    "created_visit": created_visit["id"],
                    "visits_after_create": len(visits_after_create),
                    "visits_after_delete": len(visits_after_delete),
                    "delete_result": delete_result,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
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
