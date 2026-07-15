"""Sincronizare targete agenti din Grile in `agent_targets`.

Serviciul citeste Google Sheets read-only si scrie doar override-uri sigure.
Pentru zone neactivate, target lipsa sau agent nemapat, dashboard-ul ramane pe
fallback-ul existent: target locatie / agenti activi.
"""

from __future__ import annotations

import asyncio
from hashlib import sha256
import json
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
    diff: dict[str, Any]
    read_site_codes: tuple[str, ...]

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
            "enabled_manager_count": len(self.enabled_managers),
            "disabled_manager_count": len(self.disabled_managers),
            "sites_considered": self.sites_considered,
            "sites_read": self.sites_read,
            "resolved_count": self.resolved_count,
            "unresolved_count": self.unresolved_count,
            "skipped_site_count": sum(self.skipped_managers.values()),
            "diff": self.diff,
        }


@dataclass(frozen=True)
class AgentTargetsState:
    sha256: str
    row_count: int


class AgentTargetSyncBlockedError(RuntimeError):
    pass


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
    try:
        if isinstance(value, Decimal):
            decimal_value = value
        else:
            text = str(value).strip()
            if not text:
                return None
            text = text.replace(" ", "").replace("%", "")
            if "," in text and "." in text:
                text = text.replace(".", "").replace(",", ".")
            elif "," in text:
                text = text.replace(",", ".")
            decimal_value = Decimal(text)
        if not decimal_value.is_finite() or decimal_value < 0:
            return None
        return decimal_value.quantize(Decimal("0.01"))
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
    enabled_managers: tuple[str, ...] | None = None,
    disabled_managers: tuple[str, ...] | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    fetcher: FetchAgentRanges | None = None,
) -> AgentTargetSyncResult:
    """Build a read-only target diff; applying is a separate audited operation."""
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
    candidate_site_codes = {candidate.site_code for candidate in candidates}
    empty_site_count = len(read_site_codes - candidate_site_codes)
    resolved_keys = [(row.site_code, row.agent) for row in resolved]
    duplicate_target_count = len(resolved_keys) - len(set(resolved_keys))
    current = await _load_managed_targets(
        pool,
        month=month,
        site_codes=sorted(read_site_codes),
    )
    unmanaged = await _load_unmanaged_target_keys(
        pool,
        month=month,
        site_codes=sorted(read_site_codes),
    )
    diff = _build_target_diff(current, resolved)
    diff["empty_site_count"] = empty_site_count
    diff["duplicate_target_count"] = duplicate_target_count
    diff["unmanaged_conflict_count"] = len(set(resolved_keys) & unmanaged)

    return AgentTargetSyncResult(
        month=month,
        apply=False,
        enabled_managers=enabled_managers,
        disabled_managers=disabled_managers,
        sites_considered=len(sheets),
        sites_read=len(read_site_codes),
        resolved=resolved,
        unresolved=unresolved,
        skipped_managers=skipped,
        diff=diff,
        read_site_codes=tuple(sorted(read_site_codes)),
    )


async def read_agent_targets_state(
    pool: asyncpg.Pool,
    month: str,
) -> AgentTargetsState:
    async with pool.acquire() as conn:
        return await read_agent_targets_state_on_connection(conn, month)


async def read_agent_targets_state_on_connection(
    conn: asyncpg.Connection,
    month: str,
) -> AgentTargetsState:
    rows = await conn.fetch(
        """
        SELECT site_code, agent, target_value, source_agent_name,
               source_store_key, source_file, manager, match_method
        FROM agent_targets
        WHERE import_month = $1
        ORDER BY site_code, agent
        """,
        month,
    )
    payload = [
        [
            str(row["site_code"]),
            str(row["agent"]),
            format(Decimal(row["target_value"]), "f"),
            str(row["source_agent_name"] or ""),
            str(row["source_store_key"] or ""),
            str(row["source_file"] or ""),
            str(row["manager"] or ""),
            str(row["match_method"] or ""),
        ]
        for row in rows
    ]
    digest = sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return AgentTargetsState(sha256=digest, row_count=len(payload))


def require_applicable_agent_target_sync(result: AgentTargetSyncResult) -> None:
    if (
        result.sites_read != result.sites_considered
        or result.unresolved
        or not result.read_site_codes
        or result.diff["empty_site_count"]
        or result.diff["duplicate_target_count"]
        or result.diff.get("unmanaged_conflict_count", 0)
    ):
        raise AgentTargetSyncBlockedError(
            "Sincronizarea targetelor este blocata de coverage incomplet sau erori nerezolvate."
        )


async def _load_managed_targets(
    pool: asyncpg.Pool,
    *,
    month: str,
    site_codes: list[str],
) -> dict[tuple[str, str], Decimal]:
    if not site_codes:
        return {}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT site_code, agent, target_value
            FROM agent_targets
            WHERE import_month = $1
              AND site_code = ANY($2::text[])
              AND (source_file LIKE 'grile%' OR source_file LIKE 'retail-grile%')
            """,
            month,
            site_codes,
        )
    return {
        (str(row["site_code"]), str(row["agent"])): Decimal(row["target_value"])
        for row in rows
    }


async def _load_unmanaged_target_keys(
    pool: asyncpg.Pool,
    *,
    month: str,
    site_codes: list[str],
) -> set[tuple[str, str]]:
    if not site_codes:
        return set()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT site_code, agent
            FROM agent_targets
            WHERE import_month = $1
              AND site_code = ANY($2::text[])
              AND NOT (
                COALESCE(source_file, '') LIKE 'grile%'
                OR COALESCE(source_file, '') LIKE 'retail-grile%'
              )
            """,
            month,
            site_codes,
        )
    return {(str(row["site_code"]), str(row["agent"])) for row in rows}


def _build_target_diff(
    current: dict[tuple[str, str], Decimal],
    proposed_rows: list[AgentTargetRow],
) -> dict[str, Any]:
    proposed = {
        (row.site_code, row.agent): row.target_value for row in proposed_rows
    }
    current_keys = set(current)
    proposed_keys = set(proposed)
    inserted = proposed_keys - current_keys
    deleted = current_keys - proposed_keys
    shared = current_keys & proposed_keys
    updated = {key for key in shared if current[key] != proposed[key]}
    unchanged = shared - updated
    canonical = [
        [site_code, agent, format(proposed[(site_code, agent)], "f")]
        for site_code, agent in sorted(proposed)
    ]
    proposed_sha256 = sha256(
        json.dumps(canonical, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "current_count": len(current),
        "proposed_count": len(proposed),
        "insert_count": len(inserted),
        "update_count": len(updated),
        "delete_count": len(deleted),
        "unchanged_count": len(unchanged),
        "proposed_sha256": proposed_sha256,
    }


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


async def apply_agent_target_sync_on_connection(
    conn: asyncpg.Connection,
    result: AgentTargetSyncResult,
) -> None:
    """Apply one validated diff inside a caller-owned audit transaction."""
    require_applicable_agent_target_sync(result)
    if result.resolved:
        conflicts = await conn.fetch(
            """
            SELECT existing.site_code, existing.agent
            FROM agent_targets existing
            JOIN unnest($2::text[], $3::text[]) AS proposed(site_code, agent)
              ON proposed.site_code = existing.site_code
             AND proposed.agent = existing.agent
            WHERE existing.import_month = $1
              AND NOT (
                COALESCE(existing.source_file, '') LIKE 'grile%'
                OR COALESCE(existing.source_file, '') LIKE 'retail-grile%'
              )
            FOR UPDATE OF existing
            """,
            result.month,
            [row.site_code for row in result.resolved],
            [row.agent for row in result.resolved],
        )
        if conflicts:
            raise AgentTargetSyncBlockedError(
                "Sincronizarea targetelor este blocata de targete administrate din alta sursa."
            )
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
        result.month,
        list(result.read_site_codes),
    )
    if not result.resolved:
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
        WHERE agent_targets.source_file LIKE 'grile%'
           OR agent_targets.source_file LIKE 'retail-grile%'
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
            for row in result.resolved
        ],
    )
    applied_rows = await conn.fetch(
        """
        SELECT existing.site_code, existing.agent, existing.target_value
        FROM agent_targets existing
        JOIN unnest($2::text[], $3::text[]) AS proposed(site_code, agent)
          ON proposed.site_code = existing.site_code
         AND proposed.agent = existing.agent
        WHERE existing.import_month = $1
          AND (
            existing.source_file LIKE 'grile%'
            OR existing.source_file LIKE 'retail-grile%'
          )
        """,
        result.month,
        [row.site_code for row in result.resolved],
        [row.agent for row in result.resolved],
    )
    applied = {
        (str(row["site_code"]), str(row["agent"])): Decimal(row["target_value"])
        for row in applied_rows
    }
    proposed = {
        (row.site_code, row.agent): row.target_value for row in result.resolved
    }
    if applied != proposed:
        raise AgentTargetSyncBlockedError(
            "Sincronizarea targetelor nu a putut aplica exact setul verificat."
        )
