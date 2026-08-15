"""Potriveste codurile de agent din reporting cu identitatile din salarii.

Implicit este read-only pe DB si genereaza un CSV privat in backend/outputs/.
Optiunea explicita ``--apply-db`` persista legaturile confirmate/necunoscute.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
import sys
from typing import Any, TextIO

import asyncpg
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "backend" / "outputs" / "agent_code_name_matches.csv"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

load_dotenv(REPO_ROOT / ".env.migrations")
load_dotenv(REPO_ROOT / ".env")

from db.connection import close_db_pool, get_database_url, init_db_pool
from services.spreadsheet_safety import csv_cell_value


def _open_private_csv(path: Path) -> TextIO:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    os.fchmod(fd, 0o600)
    return open(fd, "w", newline="", encoding="utf-8", closefd=True)

MANUAL_OVERRIDES: dict[tuple[str, str], dict[str, str | None]] = {
    ("AFIARAD", "ARDELEANC"): {
        "salary_full_name": "ARDELEAN EMANUELA",
        "confidence": "high",
        "note": "Confirmat manual 2026-07-04: ambiguu fata de ARDELEAN ANCA.",
    },
    ("AUCHMILI", "SANDUA"): {
        "salary_full_name": "SANDU ADRIANA",
        "confidence": "high",
        "note": "Confirmat manual 2026-07-04.",
    },
    ("AUCHMIL2", "DAVIDL"): {
        "salary_full_name": "David Larisa",
        "confidence": "high",
        "note": "Confirmat manual 2026-07-04: istoric salarial la AUCHMILI.",
    },
    ("CRFORADEA", "MESESAND"): {
        "salary_full_name": "Mesasan Cirap Daria",
        "confidence": "high",
        "note": "Confirmat in salariile HR 2026-06; ortografia oficiala este Mesasan.",
    },
    ("CLUJCFPOL", "OIOAN"): {
        "salary_full_name": "Olariu Ioan",
        "confidence": "high",
        "note": "Confirmat manual 2026-07-04.",
    },
    ("CJIULMALL", "OIOAN"): {
        "salary_full_name": "Olariu Ioan",
        "confidence": "high",
        "note": "Confirmat 2026-07-21 din istoricul salarial si mutarea raportata in 2026-07.",
    },
    ("COTROCENI", "URDAF"): {
        "salary_full_name": "URDA FLORENTINA",
        "confidence": "high",
        "note": "Confirmat manual 2026-07-04: mutata recent la Cotroceni.",
    },
    ("PITRNMT", "PLOSCARUE"): {
        "salary_full_name": "PLOSCARU ELENA",
        "confidence": "high",
        "note": "Confirmat manual 2026-07-04: salariu istoric pe PIATRANEAMT.",
    },
    ("TMACUH", "STANESCUS"): {
        "salary_full_name": "Stanescu Silvia",
        "confidence": "high",
        "note": "Confirmat in salariile HR 2026-06.",
    },
    ("CRFFEER", "PICIORUSE"): {
        "salary_full_name": "Piciorus Emanuel",
        "confidence": "high",
        "note": "Confirmat 2026-07-21 din istoricul salarial si mutarea raportata in 2026-07.",
    },
    ("DVSHP", "LUCANIUCD"): {
        "salary_full_name": None,
        "confidence": "unknown",
        "note": "Necunoscut manual 2026-07-04; poate aparea in salariile viitoare.",
    },
    ("CDVCHOP", "LUCANIUCE"): {
        "salary_full_name": None,
        "confidence": "unknown",
        "note": "Necunoscut manual 2026-07-04; poate aparea in salariile viitoare.",
    },
    ("MSBFEST", "BOBESE"): {
        "salary_full_name": None,
        "confidence": "unknown",
        "note": "Necunoscut manual 2026-07-04; poate aparea in salariile viitoare.",
    },
    ("SBFESTIV", "GODINESTEANA"): {
        "salary_full_name": None,
        "confidence": "unknown",
        "note": "Necunoscut manual 2026-07-04; poate aparea in salariile viitoare.",
    },
    ("SVIULMALL", "CHISELITAI"): {
        "salary_full_name": None,
        "confidence": "unknown",
        "note": "Necunoscut manual 2026-07-04; poate aparea in salariile viitoare.",
    },
}


def _norm(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^A-Z]", "", text.upper())


def _name_tokens(full_name: str) -> list[str]:
    return [_norm(token) for token in re.split(r"\s+", full_name.strip()) if _norm(token)]


def _common_prefix(left: str, right: str) -> int:
    count = 0
    for left_ch, right_ch in zip(left, right):
        if left_ch != right_ch:
            break
        count += 1
    return count


def _is_subsequence(needle: str, haystack: str) -> bool:
    iterator = iter(haystack)
    return all(ch in iterator for ch in needle)


def _levenshtein(left: str, right: str) -> int:
    if left == right:
        return 0
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for index, left_ch in enumerate(left, 1):
        current = [index]
        for subindex, right_ch in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[subindex] + 1,
                    previous[subindex - 1] + (left_ch != right_ch),
                )
            )
        previous = current
    return previous[-1]


def _score_code_name(agent_code: str, full_name: str) -> tuple[float, str]:
    code = _norm(agent_code)
    tokens = _name_tokens(full_name)
    if not code or not tokens:
        return -999, ""

    variants: set[str] = {"".join(tokens)}
    for index, surname in enumerate(tokens):
        if len(surname) < 3:
            continue
        others = tokens[:index] + tokens[index + 1 :]
        variants.add(surname)
        for other in others:
            variants.update(
                {
                    surname + other[:1],
                    surname + other[:2],
                    surname + other[:3],
                    surname + other,
                }
            )

    best_score = -999.0
    best_reason = ""
    for variant in variants:
        if not variant:
            continue
        prefix = _common_prefix(code, variant)
        score = float(prefix * 10)
        reason = f"prefix {prefix} vs {variant}"
        if code == variant:
            score = 200
            reason = f"exact {variant}"
        elif variant.startswith(code) and len(code) >= 4:
            score = max(score, 170 - (len(variant) - len(code)) * 2)
            reason = f"code prefix of {variant}"
        elif code.startswith(variant) and len(variant) >= 4:
            score = max(score, 165 - (len(code) - len(variant)) * 2)
            reason = f"name-code prefix {variant}"
        elif prefix >= min(5, len(code), len(variant)):
            score = max(score, 120 + prefix - abs(len(code) - len(variant)))
            reason = f"strong prefix {variant}"

        if len(code) >= 5 and _is_subsequence(code, variant):
            score = max(score, 105 - (len(variant) - len(code)))
            reason = f"subsequence {variant}"

        distance = _levenshtein(code, variant)
        if distance <= 1 and min(len(code), len(variant)) >= 5:
            score = max(score, 150 - distance * 10)
            reason = f"levenshtein {distance} {variant}"

        if score > best_score:
            best_score = float(score)
            best_reason = reason

    return best_score, best_reason


def _classify(score: float, gap: float) -> tuple[str, str]:
    if score >= 145 and gap >= 15:
        return "matched", "high"
    if score >= 105 and gap >= 20:
        return "matched", "medium"
    if score >= 80 and gap >= 25:
        return "review", "low"
    return "unmatched", "none"


async def _load_data(reporting_month: str | None) -> tuple[str, int, list[Any], list[Any], list[Any], list[Any]]:
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        latest_reporting = reporting_month or await conn.fetchval(
            "SELECT max(import_month) FROM reporting_agent_month"
        )
        latest_salary_key = await conn.fetchval("SELECT max(year * 100 + month) FROM salary_records")
        latest_year, latest_month = divmod(int(latest_salary_key), 100)
        agents = await conn.fetch(
            """
            SELECT ram.site_code, st.locatie AS current_locatie, st.firma, st.regional, st.asm,
                   ram.agent, ram.total_sales, ram.receipt_count, ram.working_days
            FROM reporting_agent_month ram
            JOIN stores st ON st.site_code = ram.site_code
            WHERE ram.import_month = $1
              AND st.is_active
              AND st.locatie NOT ILIKE 'TR %'
              AND ram.agent IS NOT NULL
              AND ram.agent <> '-'
            ORDER BY st.locatie, ram.agent
            """,
            latest_reporting,
        )
        salary_latest = await conn.fetch(
            """
            SELECT sr.site_code, sr.full_name, sr.company_name, sr.locatie,
                   sr.total_salary, sr.person_id
            FROM salary_records sr
            JOIN stores st ON st.site_code = sr.site_code
            WHERE sr.year = $1
              AND sr.month = $2
              AND st.is_active
              AND st.locatie NOT ILIKE 'TR %'
            """,
            latest_year,
            latest_month,
        )
        salary_history = await conn.fetch(
            """
            SELECT sr.site_code, sr.full_name, sr.company_name, sr.locatie,
                   sr.person_id,
                   max(sr.year * 100 + sr.month) AS last_salary_key,
                   count(DISTINCT sr.year * 100 + sr.month) AS months_seen
            FROM salary_records sr
            JOIN stores st ON st.site_code = sr.site_code
            WHERE st.is_active
              AND st.locatie NOT ILIKE 'TR %'
            GROUP BY sr.site_code, sr.full_name, sr.company_name, sr.locatie,
                     sr.person_id
            """,
        )
        salary_global_history = await conn.fetch(
            """
            SELECT sr.site_code, st.locatie AS current_locatie, sr.full_name,
                   sr.company_name, sr.person_id,
                   max(sr.year * 100 + sr.month) AS last_salary_key
            FROM salary_records sr
            JOIN stores st ON st.site_code = sr.site_code
            WHERE st.is_active
              AND st.locatie NOT ILIKE 'TR %'
            GROUP BY sr.site_code, st.locatie, sr.full_name, sr.company_name,
                     sr.person_id
            """,
        )
    await close_db_pool()
    return latest_reporting, latest_salary_key, agents, salary_latest, salary_history, salary_global_history


def _salary_indexes(salary_latest, salary_history, salary_global_history):
    latest_by_store: dict[str, list[dict[str, Any]]] = defaultdict(list)
    history_by_store: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in salary_latest:
        latest_by_store[row["site_code"]].append(dict(row))
    for row in salary_history:
        history_by_store[row["site_code"]].append(dict(row))
    person_ids_by_name: dict[str, set[str]] = defaultdict(set)
    for row in [*salary_latest, *salary_history, *salary_global_history]:
        person_id = row.get("person_id")
        if person_id:
            person_ids_by_name[_norm(row["full_name"])].add(str(person_id))
    return latest_by_store, history_by_store, person_ids_by_name


def _rank_store_candidates(
    agent_code: str,
    site_code: str,
    latest_by_store: dict[str, list[dict[str, Any]]],
    history_by_store: dict[str, list[dict[str, Any]]],
) -> list[tuple[float, str, dict[str, Any], str]]:
    candidates: list[tuple[float, str, dict[str, Any], str]] = []
    for salary_row in latest_by_store.get(site_code, []):
        score, reason = _score_code_name(agent_code, salary_row["full_name"])
        candidates.append((score, reason, salary_row, "latest_salary"))
    if not candidates or max(item[0] for item in candidates) < 75:
        for salary_row in history_by_store.get(site_code, []):
            score, reason = _score_code_name(agent_code, salary_row["full_name"])
            candidates.append((score - 20, f"history: {reason}", salary_row, "salary_history"))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates


def _automatic_match(
    candidates: list[tuple[float, str, dict[str, Any], str]],
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "matched_name": "", "person_id": None, "salary_company": "",
        "salary_locatie": "", "reason": "", "second_candidate": "",
        "score": "", "score_gap": "", "status": "no_salary_candidate",
        "confidence": "none", "match_source": "auto", "note": "",
    }
    best = candidates[0] if candidates else None
    second = candidates[1] if len(candidates) > 1 else None
    if best is None:
        return state
    salary_row = best[2]
    gap = best[0] - (second[0] if second else -999)
    status, confidence = _classify(best[0], gap)
    state.update({
        "matched_name": salary_row["full_name"],
        "person_id": salary_row.get("person_id"),
        "salary_company": salary_row.get("company_name", ""),
        "salary_locatie": salary_row.get("locatie", ""),
        "reason": best[1],
        "second_candidate": (
            f"{second[2]['full_name']} ({second[0]:.0f})" if second else ""
        ),
        "score": round(best[0], 1),
        "score_gap": round(gap, 1),
        "status": status,
        "confidence": confidence,
    })
    return state


def _apply_manual_match(
    state: dict[str, Any],
    override: dict[str, str | None] | None,
    person_ids_by_name: dict[str, set[str]],
) -> None:
    if override is None:
        return
    manual_name = override.get("salary_full_name")
    matched_name = str(manual_name) if manual_name else ""
    manual_person_ids = person_ids_by_name.get(_norm(matched_name), set())
    person_id = next(iter(manual_person_ids)) if len(manual_person_ids) == 1 else None
    status = "matched" if manual_name and person_id else "review" if manual_name else "unknown"
    state.update({
        "matched_name": matched_name,
        "person_id": person_id,
        "salary_company": "",
        "salary_locatie": "",
        "reason": "manual override",
        "second_candidate": "",
        "score": "",
        "score_gap": "",
        "status": status,
        "confidence": str(
            override.get("confidence") or ("high" if manual_name else "unknown")
        ),
        "match_source": "manual",
        "note": str(override.get("note") or ""),
    })


def _global_candidate(
    agent_code: str,
    status: str,
    salary_global_history,
) -> tuple[float, str, dict[str, Any]] | None:
    candidates: list[tuple[float, str, dict[str, Any]]] = []
    if status not in {"matched", "unknown"}:
        for salary_row in salary_global_history:
            score, reason = _score_code_name(agent_code, salary_row["full_name"])
            if score >= 100:
                candidates.append((score, reason, dict(salary_row)))
        candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0] if candidates else None


def _output_row(
    agent_row: Any,
    state: dict[str, Any],
    global_best: tuple[float, str, dict[str, Any]] | None,
) -> dict[str, Any]:
    return {
        "site_code": agent_row["site_code"],
        "magazin": agent_row["current_locatie"],
        "firma": agent_row["firma"],
        "regional": agent_row["regional"],
        "asm": agent_row["asm"],
        "agent_code": agent_row["agent"],
        "total_sales_latest_reporting": float(agent_row["total_sales"]),
        "receipt_count": agent_row["receipt_count"],
        "working_days": agent_row["working_days"],
        "matched_name": state["matched_name"],
        "person_id": state["person_id"],
        "salary_company": state["salary_company"],
        "salary_locatie": state["salary_locatie"],
        "confidence": state["confidence"],
        "status": state["status"],
        "match_source": state["match_source"],
        "score": state["score"],
        "score_gap": state["score_gap"],
        "reason": state["reason"],
        "note": state["note"],
        "second_candidate": state["second_candidate"],
        "global_candidate_name": global_best[2]["full_name"] if global_best else "",
        "global_candidate_site_code": global_best[2]["site_code"] if global_best else "",
        "global_candidate_magazin": global_best[2]["current_locatie"] if global_best else "",
        "global_candidate_score": round(global_best[0], 1) if global_best else "",
        "global_candidate_last_salary_key": global_best[2]["last_salary_key"] if global_best else "",
        "global_candidate_reason": global_best[1] if global_best else "",
    }


def _build_output_rows(agents, salary_latest, salary_history, salary_global_history):
    latest_by_store, history_by_store, person_ids = _salary_indexes(
        salary_latest, salary_history, salary_global_history
    )
    rows: list[dict[str, Any]] = []
    for agent_row in agents:
        site_code, agent_code = agent_row["site_code"], agent_row["agent"]
        state = _automatic_match(
            _rank_store_candidates(
                agent_code, site_code, latest_by_store, history_by_store
            )
        )
        _apply_manual_match(
            state, MANUAL_OVERRIDES.get((site_code, agent_code)), person_ids
        )
        global_best = _global_candidate(
            agent_code, state["status"], salary_global_history
        )
        rows.append(_output_row(agent_row, state, global_best))
    return rows


def _write_matches(path: Path, rows: list[dict[str, Any]]) -> None:
    with _open_private_csv(path) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(
            [{key: csv_cell_value(value) for key, value in row.items()} for row in rows]
        )


def _print_summary(latest_reporting: str, latest_salary_key: int, rows) -> None:
    summary = Counter(f"{row['status']}:{row['confidence']}" for row in rows)
    print(f"reporting_month={latest_reporting}")
    print(f"salary_month={latest_salary_key // 100}-{latest_salary_key % 100:02d}")
    print(f"agent_codes={len(rows)}")
    print(f"stores={len({row['site_code'] for row in rows})}")
    for key, value in sorted(summary.items()):
        print(f"{key}={value}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reporting-month", help="Implicit: ultima luna din reporting_agent_month")
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT,
        help="Fisier CSV privat generat; implicit in backend/outputs",
    )
    parser.add_argument(
        "--apply-db", action="store_true",
        help="Upsert maparile confirmate si necunoscute in agent_salary_links.",
    )
    parser.add_argument(
        "--effective-from-month",
        help="Luna efectiva YYYY-MM; implicit luna de reporting selectata.",
    )
    args = parser.parse_args()
    data = await _load_data(args.reporting_month)
    latest_reporting, latest_salary_key, agents, latest, history, global_history = data
    output_rows = _build_output_rows(agents, latest, history, global_history)
    output_path: Path = args.output.expanduser()
    _write_matches(output_path, output_rows)
    if args.apply_db:
        await _upsert_agent_salary_links(
            output_rows,
            effective_from_month=args.effective_from_month or latest_reporting,
        )
    _print_summary(latest_reporting, latest_salary_key, output_rows)
    print(f"output={output_path}")


async def _upsert_agent_salary_links(
    rows: list[dict[str, Any]],
    *,
    effective_from_month: str | None = None,
) -> None:
    if effective_from_month is not None and not re.fullmatch(
        r"\d{4}-(0[1-9]|1[0-2])",
        effective_from_month,
    ):
        raise ValueError("effective_from_month must use YYYY-MM")
    apply_db_url: str | None
    if os.getenv("UNIHUB_TEST_DATABASE") == "1":
        # Testele izolate trebuie sa domine orice URL incarcat din
        # .env.migrations; altfel un test poate ajunge accidental la DB live.
        apply_db_url = get_database_url()
    else:
        apply_db_url = os.getenv("MIGRATION_DATABASE_URL")
    if not apply_db_url:
        raise RuntimeError("MIGRATION_DATABASE_URL is required for --apply-db")
    payload: list[tuple[Any, ...]] = []
    for row in rows:
        if row["status"] not in {"matched", "unknown"}:
            continue
        salary_full_name = row["matched_name"] or None
        match_status = "confirmed" if salary_full_name else "unknown"
        person_id = row.get("person_id") if match_status == "confirmed" else None
        if match_status == "confirmed" and not person_id:
            raise ValueError("Confirmed salary link is missing person_id")
        confidence = row["confidence"] if row["confidence"] in {"high", "medium", "low"} else "unknown"
        payload.append(
            (
                row["agent_code"],
                row["site_code"],
                salary_full_name,
                None,
                match_status,
                row["match_source"],
                confidence,
                effective_from_month,
                row["note"],
                person_id,
            )
        )
    conn = await asyncpg.connect(
        apply_db_url,
        server_settings={"application_name": "unihub-retail-salary-link-import"},
    )
    try:
        await conn.executemany(
            """
            INSERT INTO agent_salary_links (
                agent_code, site_code, salary_full_name, salary_cnp,
                match_status, match_source, confidence, effective_from_month,
                note, person_id
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (agent_code, site_code) DO UPDATE
            SET salary_full_name = EXCLUDED.salary_full_name,
                salary_cnp = EXCLUDED.salary_cnp,
                match_status = EXCLUDED.match_status,
                match_source = EXCLUDED.match_source,
                confidence = EXCLUDED.confidence,
                effective_from_month = EXCLUDED.effective_from_month,
                note = EXCLUDED.note,
                person_id = EXCLUDED.person_id,
                updated_at = now()
            WHERE agent_salary_links.match_source <> 'manual'
               OR EXCLUDED.match_source = 'manual'
            """,
            payload,
        )
    finally:
        await conn.close()
    print(f"upserted_agent_salary_links={len(payload)}")


if __name__ == "__main__":
    asyncio.run(main())
