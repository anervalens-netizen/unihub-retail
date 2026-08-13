"""Pure rules and value objects for Grile agent-target synchronization."""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

AGENT_TARGET_RANGES = [
    "Grila!D2",   # Agent 1 nume
    "Grila!D8",   # Agent 1 target
    "Grila!D16",  # Agent 2 nume
    "Grila!D22",  # Agent 2 target
]
AGENT_TARGET_RANGES_V3 = [
    *AGENT_TARGET_RANGES,
    "Grila!D30",  # Agent 3 nume
    "Grila!D36",  # Agent 3 target
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


FetchAgentRanges = Callable[[str, str], list[dict[str, Any]]]


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
    slot_specs = tuple(
        (
            index // 2 + 1,
            _cell(vals[index], 0, 0),
            _cell(vals[index + 1], 0, 0),
        )
        for index in range(0, len(vals) - 1, 2)
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
