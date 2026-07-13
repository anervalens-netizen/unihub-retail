"""Sincronizare targete agenti din Grile in `agent_targets`.

Serviciul citeste Google Sheets read-only si scrie doar override-uri sigure.
Pentru zone neactivate, target lipsa sau agent nemapat, dashboard-ul ramane pe
fallback-ul existent: target locatie / agenti activi.
"""

from __future__ import annotations

import asyncio
import os
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

import asyncpg

from services.grile import _retry_sync
from services.grile_constants import (
    GOOGLE_API_RETRY_ATTEMPTS,
    GOOGLE_API_RETRY_BASE_DELAY_SECONDS,
)
from services.grile_sheets import build_services, get_credentials

AGENT_TARGET_RANGES = [
    "Grila!D2",   # Agent 1 nume
    "Grila!D8",   # Agent 1 target
    "Grila!D16",  # Agent 2 nume
    "Grila!D22",  # Agent 2 target
]

DEFAULT_ENABLED_MANAGERS = (
    "Andrei Stancu",
    "Adrian Badea",
    "Mihai Condorateanu",
    "Elena Minca",
)
DEFAULT_DISABLED_MANAGERS = ("Bogdan Radu", "Bogdana Costan")
DEFAULT_CONCURRENCY = 3
SOURCE_FILE = "retail-grile/google-sheets"

MANUAL_AGENT_OVERRIDES = {
    ("CTCORA", "DIMA CHELES VIOLETA"): "CHELESE",
    ("CRFFEER", "GOJNEA MIREL"): "GOJNEAG",
    ("CTCITYPRK", "GASCA NELA"): "GISCAN",
    ("CTCRFTOM", "CARP IULIA"): "CIULIA",
}


@dataclass(frozen=True)
class AgentTargetCandidate:
    import_month: str
    site_code: str
    source_store_key: str
    manager: str
    slot: int
    source_agent_name: str
    target_value: Decimal | None
    status: str = "candidate"


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


@dataclass(frozen=True)
class AgentTargetSyncResult:
    month: str
    apply: bool
    enabled_managers: tuple[str, ...]
    disabled_managers: tuple[str, ...]
    sites_considered: int
    sites_read: int
    resolved: list[AgentTargetRow]
    unresolved: list[dict[str, Any]]
    skipped_managers: dict[str, int]

    @property
    def resolved_count(self) -> int:
        return len(self.resolved)

    @property
    def unresolved_count(self) -> int:
        return len(self.unresolved)

    def as_dict(self) -> dict[str, Any]:
        return {
            "month": self.month,
            "apply": self.apply,
            "enabled_managers": list(self.enabled_managers),
            "disabled_managers": list(self.disabled_managers),
            "sites_considered": self.sites_considered,
            "sites_read": self.sites_read,
            "resolved_count": self.resolved_count,
            "unresolved_count": self.unresolved_count,
            "skipped_managers": self.skipped_managers,
        }


FetchAgentRanges = Callable[[str], list[dict[str, Any]]]


def configured_enabled_managers() -> tuple[str, ...]:
    return _split_env("GRILE_AGENT_TARGET_ENABLED_MANAGERS", DEFAULT_ENABLED_MANAGERS)


def configured_disabled_managers() -> tuple[str, ...]:
    return _split_env("GRILE_AGENT_TARGET_DISABLED_MANAGERS", DEFAULT_DISABLED_MANAGERS)


def _split_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None:
        return default
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def manager_is_enabled(
    manager: str | None,
    *,
    enabled_managers: tuple[str, ...],
    disabled_managers: tuple[str, ...],
) -> bool:
    if not manager or manager in disabled_managers:
        return False
    return "*" in enabled_managers or manager in enabled_managers


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


def _cell(values: list, r: int, c: int = 0) -> Any:
    try:
        v = values[r][c]
        return v if v != "" else None
    except (IndexError, TypeError):
        return None


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"))
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(" ", "").replace("%", "")
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def extract_agent_targets(
    *,
    month: str,
    site_code: str,
    manager: str,
    source_store_key: str,
    value_ranges: list[dict[str, Any]],
) -> list[AgentTargetCandidate]:
    vals = [vr.get("values", []) for vr in value_ranges]
    slot_specs = (
        (1, _cell(vals[0], 0, 0) if len(vals) > 0 else None, _cell(vals[1], 0, 0) if len(vals) > 1 else None),
        (2, _cell(vals[2], 0, 0) if len(vals) > 2 else None, _cell(vals[3], 0, 0) if len(vals) > 3 else None),
    )
    candidates: list[AgentTargetCandidate] = []
    for slot, raw_name, raw_target in slot_specs:
        agent_name = str(raw_name or "").strip()
        target = _to_decimal(raw_target)
        if not agent_name and target is None:
            continue
        status = "candidate"
        if not agent_name:
            status = "missing_agent_name"
        elif target is None:
            status = "missing_agent_target"
        candidates.append(
            AgentTargetCandidate(
                import_month=month,
                site_code=site_code,
                source_store_key=source_store_key,
                manager=manager,
                slot=slot,
                source_agent_name=agent_name,
                target_value=target,
                status=status,
            )
        )
    return candidates


def resolve_agent(
    candidate: AgentTargetCandidate,
    retail_agents: dict[str, set[str]],
) -> tuple[str | None, str]:
    normalized_name = normalize_text(candidate.source_agent_name)
    manual = MANUAL_AGENT_OVERRIDES.get((candidate.site_code, normalized_name))
    agents_for_store = retail_agents.get(candidate.site_code, set())
    if manual:
        if manual in agents_for_store:
            return manual, "manual_override"
        return None, f"manual_override_missing:{manual}"

    matches = sorted(candidate_agent_codes(candidate.source_agent_name) & agents_for_store)
    if len(matches) == 1:
        return matches[0], "auto_code"
    if len(matches) > 1:
        return None, "ambiguous_code:" + ",".join(matches)
    return None, "no_match"


def build_resolved_rows(
    candidates: list[AgentTargetCandidate],
    retail_agents: dict[str, set[str]],
) -> tuple[list[AgentTargetRow], list[dict[str, Any]]]:
    resolved: list[AgentTargetRow] = []
    unresolved: list[dict[str, Any]] = []
    for candidate in candidates:
        if candidate.status != "candidate" or candidate.target_value is None:
            unresolved.append(_candidate_to_unresolved(candidate, candidate.status))
            continue
        agent, method = resolve_agent(candidate, retail_agents)
        if not agent:
            unresolved.append(_candidate_to_unresolved(candidate, method))
            continue
        resolved.append(
            AgentTargetRow(
                import_month=candidate.import_month,
                site_code=candidate.site_code,
                agent=agent,
                target_value=candidate.target_value,
                source_agent_name=candidate.source_agent_name,
                source_store_key=candidate.source_store_key,
                manager=candidate.manager,
                match_method=method,
            )
        )
    return resolved, unresolved


def _candidate_to_unresolved(candidate: AgentTargetCandidate, status: str) -> dict[str, Any]:
    return {
        "status": status,
        "site_code": candidate.site_code,
        "source_store_key": candidate.source_store_key,
        "manager": candidate.manager,
        "slot": candidate.slot,
        "agent_name": candidate.source_agent_name,
        "target_value": candidate.target_value,
    }


async def sync_agent_targets_from_grile(
    pool: asyncpg.Pool,
    *,
    month: str,
    apply: bool = True,
    enabled_managers: tuple[str, ...] | None = None,
    disabled_managers: tuple[str, ...] | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    fetcher: FetchAgentRanges | None = None,
) -> AgentTargetSyncResult:
    enabled_managers = enabled_managers or configured_enabled_managers()
    disabled_managers = disabled_managers or configured_disabled_managers()
    sheets, skipped = await _load_enabled_sheets(
        pool,
        enabled_managers=enabled_managers,
        disabled_managers=disabled_managers,
    )
    candidates, read_site_codes, read_errors = await _read_candidates(
        month=month,
        sheets=sheets,
        concurrency=concurrency,
        fetcher=fetcher,
    )
    retail_agents = await _load_retail_agents(pool, month, sorted(read_site_codes))
    resolved, unresolved = build_resolved_rows(candidates, retail_agents)
    unresolved.extend(read_errors)

    if apply and read_site_codes:
        await _replace_agent_targets(
            pool,
            month=month,
            read_site_codes=sorted(read_site_codes),
            rows=resolved,
        )

    return AgentTargetSyncResult(
        month=month,
        apply=apply,
        enabled_managers=enabled_managers,
        disabled_managers=disabled_managers,
        sites_considered=len(sheets),
        sites_read=len(read_site_codes),
        resolved=resolved,
        unresolved=unresolved,
        skipped_managers=skipped,
    )


async def _load_enabled_sheets(
    pool: asyncpg.Pool,
    *,
    enabled_managers: tuple[str, ...],
    disabled_managers: tuple[str, ...],
) -> tuple[list[asyncpg.Record], dict[str, int]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT gs.site_code, gs.sheet_id, gs.registry_key, s.asm AS manager
            FROM grile_sheets gs
            JOIN stores s ON s.site_code = gs.site_code
            WHERE gs.is_active = true
            ORDER BY s.asm, gs.site_code
            """
        )
    enabled: list[asyncpg.Record] = []
    skipped: dict[str, int] = {}
    for row in rows:
        manager = row["manager"] or ""
        if manager_is_enabled(
            manager,
            enabled_managers=enabled_managers,
            disabled_managers=disabled_managers,
        ):
            enabled.append(row)
        else:
            skipped[manager or "Neatribuit"] = skipped.get(manager or "Neatribuit", 0) + 1
    return enabled, skipped


async def _read_candidates(
    *,
    month: str,
    sheets: list[asyncpg.Record],
    concurrency: int,
    fetcher: FetchAgentRanges | None,
) -> tuple[list[AgentTargetCandidate], set[str], list[dict[str, Any]]]:
    if not sheets:
        return [], set(), []

    if fetcher is None:
        await asyncio.to_thread(get_credentials)
        fetcher = _build_google_fetcher(concurrency)

    semaphore = asyncio.Semaphore(concurrency)
    candidates: list[AgentTargetCandidate] = []
    read_site_codes: set[str] = set()
    errors: list[dict[str, Any]] = []

    async def process(sheet: asyncpg.Record) -> None:
        async with semaphore:
            site_code = sheet["site_code"]
            try:
                value_ranges = await asyncio.to_thread(fetcher, sheet["sheet_id"])
                candidates.extend(
                    extract_agent_targets(
                        month=month,
                        site_code=site_code,
                        manager=sheet["manager"] or "",
                        source_store_key=sheet["registry_key"] or site_code,
                        value_ranges=value_ranges,
                    )
                )
                read_site_codes.add(site_code)
            except Exception as exc:  # noqa: BLE001 - eroare per sheet, nu opreste syncul
                errors.append(
                    {
                        "status": "google_error",
                        "site_code": site_code,
                        "source_store_key": sheet["registry_key"] or site_code,
                        "manager": sheet["manager"],
                        "error": str(exc)[:500],
                    }
                )

    await asyncio.gather(*(process(sheet) for sheet in sheets))
    return candidates, read_site_codes, errors


def _build_google_fetcher(concurrency: int) -> FetchAgentRanges:
    local = threading.local()
    lock = threading.Lock()
    last_call = {"ts": 0.0}
    min_interval = 60.0 / max(concurrency * 20, 1)

    def _service() -> Any:
        if not hasattr(local, "sheets"):
            local.sheets, _ = build_services()
        return local.sheets

    def fetch(sheet_id: str) -> list[dict[str, Any]]:
        with lock:
            elapsed = time.monotonic() - last_call["ts"]
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            last_call["ts"] = time.monotonic()
        sheets_svc = _service()
        return _retry_sync(
            lambda: sheets_svc.spreadsheets().values().batchGet(
                spreadsheetId=sheet_id,
                ranges=AGENT_TARGET_RANGES,
                valueRenderOption="UNFORMATTED_VALUE",
            ).execute().get("valueRanges", []),
            attempts=GOOGLE_API_RETRY_ATTEMPTS,
            base_delay=GOOGLE_API_RETRY_BASE_DELAY_SECONDS,
        )

    return fetch


async def _load_retail_agents(
    pool: asyncpg.Pool,
    month: str,
    site_codes: list[str],
) -> dict[str, set[str]]:
    if not site_codes:
        return {}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT site_code, agent
            FROM reporting_agent_month
            WHERE import_month = $1
              AND site_code = ANY($2::TEXT[])
              AND agent IS NOT NULL
              AND agent != '-'
            ORDER BY site_code, agent
            """,
            month,
            site_codes,
        )
    result: dict[str, set[str]] = {}
    for row in rows:
        result.setdefault(row["site_code"], set()).add(row["agent"])
    return result


async def _replace_agent_targets(
    pool: asyncpg.Pool,
    *,
    month: str,
    read_site_codes: list[str],
    rows: list[AgentTargetRow],
) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                DELETE FROM agent_targets
                WHERE import_month = $1
                  AND site_code = ANY($2::TEXT[])
                  AND (
                    source_file LIKE 'grile%'
                    OR source_file LIKE 'retail-grile%'
                  )
                """,
                month,
                read_site_codes,
            )
            if not rows:
                return
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
                        SOURCE_FILE,
                        row.manager,
                        row.match_method,
                    )
                    for row in rows
                ],
            )
