"""Pure P&L authority and generation contract values."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID


COMPANIES = frozenset({"Mobicell", "Mobiup"})
HEX64 = set("0123456789abcdef")
CENT = Decimal("0.01")
PnlScope = tuple[str, date]
PnlBusinessKey = tuple[str, date, str, str]


class PnlImportError(RuntimeError):
    """A requested Finance import breaks the explicit-authority contract."""


class PnlGenerationConflict(PnlImportError):
    """A staged generation no longer matches the current P&L head."""


@dataclass(frozen=True)
class PnlRow:
    company_name: str
    period: date
    source_site_code: str
    source_location_name: str
    category_code: str
    category_name: str
    amount: Decimal
    source_file: str
    source_sha256: str


@dataclass(frozen=True)
class AuthorityScope:
    company_name: str
    period: date
    revision_id: str
    parent_revision_id: str
    cutoff: date
    source_path: str
    source_sha256: str
    expected_row_count: int
    expected_total_amount: Decimal
    coverage_sha256: str

    @property
    def key(self) -> PnlScope:
        return self.company_name, self.period


@dataclass(frozen=True)
class AuthorityManifest:
    version: int
    approval_id: str
    scopes: tuple[AuthorityScope, ...]
    sha256: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class StageResult:
    generation_id: UUID
    generation_manifest_sha256: str
    generation_manifest: dict[str, Any]


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    return value


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        _canonical_value(value),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX64


def _month(value: object, *, field: str) -> date:
    if not isinstance(value, str):
        raise PnlImportError(f"{field} trebuie sa fie YYYY-MM-DD.")
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise PnlImportError(f"{field} trebuie sa fie YYYY-MM-DD.") from exc
    if result.day != 1:
        raise PnlImportError(f"{field} trebuie sa fie prima zi din luna.")
    return result


def _cutoff(value: object) -> date:
    if not isinstance(value, str):
        raise PnlImportError("cutoff trebuie sa fie YYYY-MM-DD.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise PnlImportError("cutoff trebuie sa fie YYYY-MM-DD.") from exc


def _relative_source_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise PnlImportError("source_path lipseste din authority manifest.")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or str(path) in {".", ""}:
        raise PnlImportError("source_path trebuie sa fie relativ si fara '..'.")
    return str(path)



def row_payload(row: PnlRow) -> dict[str, Any]:
    return {
        "company_name": row.company_name,
        "period": row.period,
        "source_site_code": row.source_site_code,
        "source_location_name": row.source_location_name,
        "category_code": row.category_code,
        "category_name": row.category_name,
        "amount": row.amount,
        "source_file": row.source_file,
        "source_sha256": row.source_sha256,
    }


def _digest_scalar(value: object) -> str:
    if isinstance(value, Decimal):
        text = format(value, "f")
    elif isinstance(value, date):
        text = value.isoformat()
    else:
        text = str(value)
    return f"V{len(text.encode('utf-8'))}:{text}"


def _row_digest_payload(row: PnlRow) -> str:
    return "\x1f".join(
        _digest_scalar(value)
        for value in (
            row.company_name,
            row.period,
            row.source_site_code,
            row.source_location_name,
            row.category_code,
            row.category_name,
            row.amount,
            row.source_file,
            row.source_sha256,
        )
    )


def normalized_rows(rows: Iterable[PnlRow]) -> list[dict[str, Any]]:
    return [
        row_payload(row)
        for row in sorted(rows, key=business_key)
    ]


def rows_sha256(rows: Iterable[PnlRow]) -> str:
    payload = "\x1e".join(
        _row_digest_payload(row)
        for row in sorted(rows, key=business_key)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def business_key(row: PnlRow) -> PnlBusinessKey:
    return row.company_name, row.period, row.source_site_code, row.category_code


def coverage_sha256(rows: Iterable[PnlRow]) -> str:
    payload = "\x1e".join(
        "\x1f".join(_digest_scalar(value) for value in key)
        for key in sorted({business_key(row) for row in rows})
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def ensure_unique_business_keys(rows: Sequence[PnlRow]) -> None:
    keys = {business_key(row) for row in rows}
    if len(keys) != len(rows):
        raise PnlImportError("Batchul P&L contine chei business duplicate.")


def scope_totals(rows: Iterable[PnlRow]) -> tuple[int, Decimal]:
    values = list(rows)
    return len(values), sum((row.amount for row in values), Decimal("0.00"))


def validate_scope_candidate(scope: AuthorityScope, rows: Sequence[PnlRow]) -> None:
    if not rows:
        raise PnlImportError(f"Snapshot Finance gol pentru {scope.company_name} {scope.period:%Y-%m}.")
    if any((row.company_name, row.period) != scope.key for row in rows):
        raise PnlImportError("Candidatele P&L ies din scope-ul authority manifest.")
    if any(
        (row.source_file, row.source_sha256) != (scope.source_path, scope.source_sha256)
        for row in rows
    ):
        raise PnlImportError("Randurile P&L nu provin exact din sursa authority declarata.")
    if any(not row.amount.is_finite() or row.amount != row.amount.quantize(CENT) for row in rows):
        raise PnlImportError("Sumele candidate P&L trebuie sa fie finite si rotunjite la 0.01.")
    ensure_unique_business_keys(rows)
    row_count, total = scope_totals(rows)
    if row_count != scope.expected_row_count or total != scope.expected_total_amount:
        raise PnlImportError(
            f"Control totals Finance nu corespund manifestului pentru {scope.company_name} {scope.period:%Y-%m}."
        )
    if coverage_sha256(rows) != scope.coverage_sha256:
        raise PnlImportError(
            f"Coverage Finance nu corespunde manifestului pentru {scope.company_name} {scope.period:%Y-%m}."
        )


def coverage_regressions(current_rows: Sequence[PnlRow], candidate_rows: Sequence[PnlRow]) -> list[PnlBusinessKey]:
    ensure_unique_business_keys(candidate_rows)
    return sorted({business_key(row) for row in current_rows} - {business_key(row) for row in candidate_rows})
