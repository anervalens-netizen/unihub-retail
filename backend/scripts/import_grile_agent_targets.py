#!/usr/bin/env python3
"""Import targete reale per agent din Grile Salarii in Retail.

Pilotul curent importa doar magazinele managerului Andrei Stancu din
`/opt/Mobiup/grile-salarii`, folosind `store_metadata.json` pentru site_code
si `outputs/monitor_output.json` pentru nume/target agent.

Default ruleaza dry-run. Foloseste `--apply` pentru upsert in `agent_targets`.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = ROOT_DIR.parent
load_dotenv(REPO_DIR / ".env")
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db.connection import close_db_pool, ensure_schema_current, get_pool, init_db_pool

GRILE_ROOT = Path("/opt/Mobiup/grile-salarii")
DEFAULT_MANAGER = "Andrei Stancu"

MANUAL_AGENT_OVERRIDES = {
    ("CTCORA", "DIMA CHELES VIOLETA"): "CHELESE",
    ("CRFFEER", "GOJNEA MIREL"): "GOJNEAG",
    ("CTCITYPRK", "GASCA NELA"): "GISCAN",
    ("CTCRFTOM", "CARP IULIA"): "CIULIA",
}


@dataclass(frozen=True)
class AgentTargetRow:
    import_month: str
    site_code: str
    agent: str
    target_value: Decimal
    source_agent_name: str
    source_store_key: str
    manager: str
    match_method: str


def normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9 ]+", " ", text).upper()
    return " ".join(text.split())


def name_tokens(value: str) -> list[str]:
    return [token for token in normalize_text(value).split() if len(token) > 1]


def candidate_agent_codes(name: str) -> set[str]:
    tokens = name_tokens(name)
    candidates: set[str] = set()
    for last_idx, last_name in enumerate(tokens):
        for first_idx, first_name in enumerate(tokens):
            if last_idx == first_idx:
                continue
            for prefix_len in (1, 2, 3, 4):
                candidates.add(last_name + first_name[:prefix_len])
            candidates.add(last_name[:8] + first_name[:1])
    return candidates


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def collect_grile_rows(
    *,
    grile_root: Path,
    manager: str,
    month: str,
) -> list[dict[str, Any]]:
    metadata = load_json(grile_root / "store_metadata.json")
    monitor_rows = load_json(grile_root / "outputs" / "monitor_output.json")
    monitor_by_key = {
        f"{row.get('company')}/{row.get('store')}": row for row in monitor_rows
    }

    rows: list[dict[str, Any]] = []
    for store_key, meta in metadata.items():
        if store_key.startswith("_") or meta.get("manager") != manager:
            continue
        site_code = str(meta.get("cod_locatie") or "").strip()
        if not site_code:
            rows.append(
                {
                    "status": "missing_site_code",
                    "store_key": store_key,
                    "site_code": "",
                    "agent_name": "",
                    "target_value": None,
                }
            )
            continue
        monitor = monitor_by_key.get(store_key)
        if not monitor:
            rows.append(
                {
                    "status": "missing_monitor",
                    "store_key": store_key,
                    "site_code": site_code,
                    "agent_name": "",
                    "target_value": None,
                }
            )
            continue

        for slot in ("agent1", "agent2"):
            agent_data = monitor.get(slot) or {}
            agent_name = str(agent_data.get("nume") or "").strip()
            target = agent_data.get("target")
            if not agent_name or target in (None, ""):
                rows.append(
                    {
                        "status": "missing_agent_target",
                        "store_key": store_key,
                        "site_code": site_code,
                        "agent_name": agent_name,
                        "target_value": target,
                    }
                )
                continue
            rows.append(
                {
                    "status": "candidate",
                    "import_month": month,
                    "store_key": store_key,
                    "site_code": site_code,
                    "agent_name": agent_name,
                    "target_value": Decimal(str(target)).quantize(Decimal("0.01")),
                }
            )
    return rows


async def load_retail_agents(conn: Any, month: str, site_codes: list[str]) -> dict[str, set[str]]:
    rows = await conn.fetch(
        """
        SELECT site_code, agent
        FROM reporting_agent_month
        WHERE import_month = $1
          AND site_code = ANY($2::TEXT[])
        ORDER BY site_code, agent
        """,
        month,
        site_codes,
    )
    result: dict[str, set[str]] = {}
    for row in rows:
        result.setdefault(row["site_code"], set()).add(row["agent"])
    return result


def resolve_agent(row: dict[str, Any], retail_agents: dict[str, set[str]]) -> tuple[str | None, str]:
    site_code = row["site_code"]
    agent_name = row["agent_name"]
    normalized_name = normalize_text(agent_name)
    manual = MANUAL_AGENT_OVERRIDES.get((site_code, normalized_name))
    agents_for_store = retail_agents.get(site_code, set())
    if manual:
        if manual in agents_for_store:
            return manual, "manual_override"
        return None, f"manual_override_missing:{manual}"

    candidates = candidate_agent_codes(agent_name)
    matches = sorted(candidates & agents_for_store)
    if len(matches) == 1:
        return matches[0], "auto_code"
    if len(matches) > 1:
        return None, "ambiguous_code:" + ",".join(matches)
    return None, "no_match"


async def upsert_rows(conn: Any, rows: list[AgentTargetRow]) -> None:
    await conn.executemany(
        """
        INSERT INTO agent_targets (
            import_month,
            site_code,
            agent,
            target_value,
            source_agent_name,
            source_store_key,
            source_file,
            manager,
            match_method,
            updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, now())
        ON CONFLICT (import_month, site_code, agent) DO UPDATE
        SET target_value = EXCLUDED.target_value,
            source_agent_name = EXCLUDED.source_agent_name,
            source_store_key = EXCLUDED.source_store_key,
            source_file = EXCLUDED.source_file,
            manager = EXCLUDED.manager,
            match_method = EXCLUDED.match_method,
            updated_at = now()
        """,
        [
            (
                row.import_month,
                row.site_code,
                row.agent,
                row.target_value,
                row.source_agent_name,
                row.source_store_key,
                "grile-salarii/outputs/monitor_output.json",
                row.manager,
                row.match_method,
            )
            for row in rows
        ],
    )


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Importa targete reale per agent din Grile Salarii in Retail."
    )
    parser.add_argument("--month", required=True, help="Luna Retail, format YYYY-MM")
    parser.add_argument("--manager", default=DEFAULT_MANAGER)
    parser.add_argument("--grile-root", default=str(GRILE_ROOT))
    parser.add_argument("--apply", action="store_true", help="Scrie in agent_targets")
    args = parser.parse_args()

    grile_root = Path(args.grile_root)
    raw_rows = collect_grile_rows(
        grile_root=grile_root,
        manager=args.manager,
        month=args.month,
    )
    site_codes = sorted(
        {row["site_code"] for row in raw_rows if row.get("site_code")}
    )

    await init_db_pool()
    await ensure_schema_current()
    pool = await get_pool()
    async with pool.acquire() as conn:
        retail_agents = await load_retail_agents(conn, args.month, site_codes)
        resolved: list[AgentTargetRow] = []
        unresolved: list[dict[str, Any]] = []

        for row in raw_rows:
            if row["status"] != "candidate":
                unresolved.append(row)
                continue
            agent, method = resolve_agent(row, retail_agents)
            if not agent:
                unresolved.append({**row, "status": method})
                continue
            resolved.append(
                AgentTargetRow(
                    import_month=args.month,
                    site_code=row["site_code"],
                    agent=agent,
                    target_value=row["target_value"],
                    source_agent_name=row["agent_name"],
                    source_store_key=row["store_key"],
                    manager=args.manager,
                    match_method=method,
                )
            )

        print(f"Manager: {args.manager}")
        print(f"Luna: {args.month}")
        print(f"Magazine pilot: {len(site_codes)}")
        print(f"Targete rezolvate: {len(resolved)}")
        print(f"Nerezolvate: {len(unresolved)}")

        if unresolved:
            print("\nNEREZOLVATE")
            for unresolved_row in unresolved:
                agents = ", ".join(
                    sorted(retail_agents.get(unresolved_row.get("site_code", ""), set()))
                )
                print(
                    f"- {unresolved_row.get('site_code')} | {unresolved_row.get('store_key')} | "
                    f"{unresolved_row.get('agent_name')} | target={unresolved_row.get('target_value')} | "
                    f"status={unresolved_row.get('status')} | retail_agents={agents}"
                )

        print("\nREZOLVATE")
        for resolved_row in resolved:
            print(
                f"- {resolved_row.site_code} | "
                f"{resolved_row.source_agent_name} -> {resolved_row.agent} | "
                f"target={resolved_row.target_value} | {resolved_row.match_method}"
            )

        if args.apply:
            if unresolved:
                raise SystemExit("Refuz apply: exista randuri nerezolvate.")
            async with conn.transaction():
                await upsert_rows(conn, resolved)
            print(f"\nImport finalizat: {len(resolved)} randuri upsert in agent_targets.")
        else:
            print("\nDRY RUN: nu s-a scris nimic. Ruleaza cu --apply pentru import.")

    await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
