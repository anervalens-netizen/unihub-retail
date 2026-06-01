"""Proxy catre grile-salarii pentru operatiile de inchidere luna.

Operatiile WRITE (finalize/archive/reset) raman in app-ul grile-salarii
(`/opt/Mobiup/grile-salarii`): acolo sunt scripturile validate + service
account-ul Google cu drept de Editor. Retail NU primeste write-capability pe
Google; doar DELEGHEAZA pe localhost catre grile-salarii, cu un secret intern.

Apelurile sunt lente (zeci de magazine -> minute), deci ruleaza in worker (arq)
ca sa nu loveasca timeout-ul de edge Cloudflare. Aici e doar logica de proxy.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

# Citite lazy (nu la import) ca sa fie sigure fata de ordinea load_dotenv vs import.
def _base_url() -> str:
    return os.getenv("GRILE_BASE_URL", "http://127.0.0.1:47000")


def _secret() -> str:
    return os.getenv("GRILE_INTERNAL_SECRET", "")


# subprocess-ul din grile-salarii are timeout=600s; lasam un pic peste
_TIMEOUT = httpx.Timeout(660.0, connect=10.0)

RO_MONTHS = [
    "", "Ianuarie", "Februarie", "Martie", "Aprilie", "Mai", "Iunie",
    "Iulie", "August", "Septembrie", "Octombrie", "Noiembrie", "Decembrie",
]

VALID_OPS = {"finalize", "archive", "reset"}
VALID_DOWNLOADS = {"final": "final", "archive": "archive"}


def ro_month_label(ym: str) -> str:
    """`2026-05` -> `Mai 2026` (formatul folosit de grile-salarii)."""
    year, month = ym.split("-")
    return f"{RO_MONTHS[int(month)]} {year}"


def next_ym(ym: str) -> str:
    """`2026-05` -> `2026-06` (rollover decembrie -> ianuarie)."""
    year, month = (int(x) for x in ym.split("-"))
    month += 1
    if month > 12:
        month = 1
        year += 1
    return f"{year:04d}-{month:02d}"


def _headers() -> dict[str, str]:
    secret = _secret()
    if not secret:
        raise RuntimeError(
            "GRILE_INTERNAL_SECRET nu e setat in retail; proxy-ul catre grile-salarii e dezactivat."
        )
    return {"X-Grile-Internal": secret}


async def run_monthly_op(
    *,
    op: str,
    month: str,
    only: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Apeleaza endpoint-ul corespunzator din grile-salarii. Ruleaza in worker."""
    if op not in VALID_OPS:
        raise ValueError(f"Operatie necunoscuta: {op}")

    month_label = ro_month_label(month)
    params: dict[str, Any]
    if op == "reset":
        params = {
            "closing_month": month_label,
            "next_month": ro_month_label(next_ym(month)),
            "dry_run": dry_run,
        }
    else:
        params = {"month": month_label}
    if only:
        params["only"] = only

    path = f"/api/{op}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(f"{_base_url()}{path}", params=params, headers=_headers())
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:1000]
        return {
            "op": op, "month_label": month_label, "status": "failed",
            "output": f"HTTP {exc.response.status_code} de la grile-salarii:\n{body}",
            "exit_code": exc.response.status_code,
        }
    except Exception as exc:  # noqa: BLE001 — orice eroare de retea -> raport curat
        return {
            "op": op, "month_label": month_label, "status": "failed",
            "output": f"Eroare la apelul grile-salarii: {exc}", "exit_code": -1,
        }

    return {
        "op": op,
        "month_label": month_label,
        "status": data.get("status", "failed"),
        "output": data.get("output", ""),
        "exit_code": data.get("exit_code"),
        "dry_run": data.get("dry_run", dry_run if op == "reset" else None),
    }


async def fetch_download(kind: str, month: str) -> tuple[bytes, str, str]:
    """Descarca fisierul generat (final XLSX / archive ZIP). Rapid -> sincron OK.

    Returneaza (continut, filename, media_type). Ridica FileNotFoundError daca
    grile-salarii nu are fisierul (nu s-a rulat inca finalize/archive).
    """
    if kind not in VALID_DOWNLOADS:
        raise ValueError(f"Tip download necunoscut: {kind}")
    month_label = ro_month_label(month)
    url = f"{_base_url()}/api/download/{kind}/{month_label}"
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
        resp = await client.get(url, headers=_headers())
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "")
        # grile-salarii intoarce JSON {"error": ...} cu 200 cand fisierul lipseste
        if ctype.startswith("application/json"):
            raise FileNotFoundError(
                f"Fisierul {kind} pentru {month_label} nu exista inca (ruleaza intai operatia)."
            )
        if kind == "final":
            filename = f"Tabel Salarii - {month_label}.xlsx"
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        else:
            filename = f"Arhiva Grile - {month_label}.zip"
            media_type = "application/zip"
        return resp.content, filename, media_type
