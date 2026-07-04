"""Potriveste codurile de agent din reporting cu numele din salarii.

Script read-only pe DB. Genereaza un CSV in reports/ cu potriviri automate si
cazuri de verificat manual.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.connection import close_db_pool, init_db_pool

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
        "salary_full_name": "Mesesan Cirap Daria",
        "confidence": "high",
        "note": "Confirmat manual 2026-07-04: angajat nou, asteptat in salariile din 2026-06.",
    },
    ("CLUJCFPOL", "OIOAN"): {
        "salary_full_name": "Olariu Ioan",
        "confidence": "high",
        "note": "Confirmat manual 2026-07-04.",
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
        "note": "Confirmat manual 2026-07-04: angajat nou, asteptat in salariile din 2026-06.",
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
            SELECT sr.site_code, sr.full_name, sr.company_name, sr.locatie, sr.total_salary, sr.cnp
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
                   max(sr.year * 100 + sr.month) AS last_salary_key,
                   count(DISTINCT sr.year * 100 + sr.month) AS months_seen
            FROM salary_records sr
            JOIN stores st ON st.site_code = sr.site_code
            WHERE st.is_active
              AND st.locatie NOT ILIKE 'TR %'
            GROUP BY sr.site_code, sr.full_name, sr.company_name, sr.locatie
            """,
        )
        salary_global_history = await conn.fetch(
            """
            SELECT sr.site_code, st.locatie AS current_locatie, sr.full_name, sr.company_name,
                   max(sr.year * 100 + sr.month) AS last_salary_key
            FROM salary_records sr
            JOIN stores st ON st.site_code = sr.site_code
            WHERE st.is_active
              AND st.locatie NOT ILIKE 'TR %'
            GROUP BY sr.site_code, st.locatie, sr.full_name, sr.company_name
            """,
        )
    await close_db_pool()
    return latest_reporting, latest_salary_key, agents, salary_latest, salary_history, salary_global_history


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reporting-month", help="Implicit: ultima luna din reporting_agent_month")
    parser.add_argument(
        "--output",
        default="reports/agent_code_name_matches.csv",
        help="Fisier CSV generat",
    )
    parser.add_argument(
        "--apply-db",
        action="store_true",
        help="Upsert maparile confirmate si necunoscute in agent_salary_links.",
    )
    args = parser.parse_args()

    (
        latest_reporting,
        latest_salary_key,
        agents,
        salary_latest,
        salary_history,
        salary_global_history,
    ) = await _load_data(args.reporting_month)

    latest_by_store: dict[str, list[dict[str, Any]]] = defaultdict(list)
    history_by_store: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in salary_latest:
        latest_by_store[row["site_code"]].append(dict(row))
    for row in salary_history:
        history_by_store[row["site_code"]].append(dict(row))

    output_rows: list[dict[str, Any]] = []
    for agent_row in agents:
        site_code = agent_row["site_code"]
        agent_code = agent_row["agent"]
        manual_override = MANUAL_OVERRIDES.get((site_code, agent_code))
        candidates: list[tuple[float, str, dict[str, Any], str]] = []

        for salary_row in latest_by_store.get(site_code, []):
            score, reason = _score_code_name(agent_code, salary_row["full_name"])
            candidates.append((score, reason, salary_row, "latest_salary"))

        if not candidates or max(item[0] for item in candidates) < 75:
            for salary_row in history_by_store.get(site_code, []):
                score, reason = _score_code_name(agent_code, salary_row["full_name"])
                candidates.append((score - 20, f"history: {reason}", salary_row, "salary_history"))

        candidates.sort(key=lambda item: item[0], reverse=True)
        best = candidates[0] if candidates else None
        second = candidates[1] if len(candidates) > 1 else None

        matched_name = ""
        salary_company = ""
        salary_locatie = ""
        reason = ""
        second_candidate = ""
        score: float | str = ""
        gap: float | str = ""
        status = "no_salary_candidate"
        confidence = "none"

        if best:
            score = round(best[0], 1)
            reason = best[1]
            salary_row = best[2]
            matched_name = salary_row["full_name"]
            salary_company = salary_row.get("company_name", "")
            salary_locatie = salary_row.get("locatie", "")
            gap_value = best[0] - (second[0] if second else -999)
            gap = round(gap_value, 1)
            status, confidence = _classify(best[0], gap_value)
            if second:
                second_candidate = f"{second[2]['full_name']} ({second[0]:.0f})"

        match_source = "auto"
        note = ""
        if manual_override is not None:
            match_source = "manual"
            note = str(manual_override.get("note") or "")
            manual_name = manual_override.get("salary_full_name")
            matched_name = str(manual_name) if manual_name else ""
            salary_company = ""
            salary_locatie = ""
            status = "matched" if manual_name else "unknown"
            confidence = str(manual_override.get("confidence") or ("high" if manual_name else "unknown"))
            score = ""
            gap = ""
            reason = "manual override"
            second_candidate = ""

        global_candidates: list[tuple[float, str, dict[str, Any]]] = []
        if status not in {"matched", "unknown"}:
            for salary_row in salary_global_history:
                global_score, global_reason = _score_code_name(agent_code, salary_row["full_name"])
                if global_score >= 100:
                    global_candidates.append((global_score, global_reason, dict(salary_row)))
            global_candidates.sort(key=lambda item: item[0], reverse=True)
        global_best = global_candidates[0] if global_candidates else None

        output_rows.append(
            {
                "site_code": site_code,
                "magazin": agent_row["current_locatie"],
                "firma": agent_row["firma"],
                "regional": agent_row["regional"],
                "asm": agent_row["asm"],
                "agent_code": agent_code,
                "total_sales_latest_reporting": float(agent_row["total_sales"]),
                "receipt_count": agent_row["receipt_count"],
                "working_days": agent_row["working_days"],
                "matched_name": matched_name,
                "salary_company": salary_company,
                "salary_locatie": salary_locatie,
                "confidence": confidence,
                "status": status,
                "match_source": match_source,
                "score": score,
                "score_gap": gap,
                "reason": reason,
                "note": note,
                "second_candidate": second_candidate,
                "global_candidate_name": global_best[2]["full_name"] if global_best else "",
                "global_candidate_site_code": global_best[2]["site_code"] if global_best else "",
                "global_candidate_magazin": global_best[2]["current_locatie"] if global_best else "",
                "global_candidate_score": round(global_best[0], 1) if global_best else "",
                "global_candidate_last_salary_key": global_best[2]["last_salary_key"] if global_best else "",
                "global_candidate_reason": global_best[1] if global_best else "",
            }
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output_rows[0].keys()))
        writer.writeheader()
        writer.writerows(output_rows)

    if args.apply_db:
        await _upsert_agent_salary_links(output_rows)

    summary = Counter(f"{row['status']}:{row['confidence']}" for row in output_rows)
    print(f"reporting_month={latest_reporting}")
    print(f"salary_month={latest_salary_key // 100}-{latest_salary_key % 100:02d}")
    print(f"agent_codes={len(output_rows)}")
    print(f"stores={len({row['site_code'] for row in output_rows})}")
    for key, value in sorted(summary.items()):
        print(f"{key}={value}")
    print(f"output={output_path}")


async def _upsert_agent_salary_links(rows: list[dict[str, Any]]) -> None:
    pool = await init_db_pool()
    payload: list[tuple[Any, ...]] = []
    for row in rows:
        if row["status"] not in {"matched", "unknown"}:
            continue
        salary_full_name = row["matched_name"] or None
        match_status = "confirmed" if salary_full_name else "unknown"
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
                "2026-07",
                row["note"],
            )
        )
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO agent_salary_links (
                agent_code, site_code, salary_full_name, salary_cnp,
                match_status, match_source, confidence, effective_from_month, note
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (agent_code, site_code) DO UPDATE
            SET salary_full_name = EXCLUDED.salary_full_name,
                salary_cnp = EXCLUDED.salary_cnp,
                match_status = EXCLUDED.match_status,
                match_source = EXCLUDED.match_source,
                confidence = EXCLUDED.confidence,
                effective_from_month = EXCLUDED.effective_from_month,
                note = EXCLUDED.note,
                updated_at = now()
            """,
            payload,
        )
    await close_db_pool()
    print(f"upserted_agent_salary_links={len(payload)}")


if __name__ == "__main__":
    asyncio.run(main())
