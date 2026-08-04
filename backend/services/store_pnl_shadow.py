"""Repeatable-read, non-mutating provenance for P&L TVA shadow candidates."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import asyncpg

from scripts import estimate_store_pnl as estimator
from services.fiscal_rules import LEGACY_VAT_RULESET_ID, standard_vat_ruleset_hash


class ShadowGenerationError(RuntimeError):
    """A requested shadow operation violates its immutable review contract."""


class PointerRevisionMismatch(ShadowGenerationError):
    """The caller attempted a stale compare-and-swap pointer update."""


class EffectivePromotionBlocked(ShadowGenerationError):
    """Effective VAT rows may not be applied by this release."""


Scope = tuple[str, date]


@dataclass(frozen=True)
class ShadowCapture:
    scopes: tuple[Scope, ...]
    input_cutoff: date
    source_sha256: str
    input_sha256: str
    legacy_ruleset_sha256: str
    effective_ruleset_sha256: str
    legacy_model_sha256: str
    effective_model_sha256: str
    legacy_output_sha256: str
    effective_output_sha256: str
    fiscal_delta: dict[str, Any]
    input_or_model_delta: dict[str, Any]
    baseline_generation_id: UUID | None
    preimage_rows: tuple[dict[str, Any], ...]
    legacy_rows: tuple[estimator.Estimate, ...]
    effective_rows: tuple[estimator.Estimate, ...]

    @property
    def scope_sha256(self) -> str:
        return canonical_sha256(scope_payload(self.scopes))

    def report(self) -> dict[str, Any]:
        return {
            "scope": scope_payload(self.scopes),
            "input_cutoff": self.input_cutoff.isoformat(),
            "source_sha256": self.source_sha256,
            "input_sha256": self.input_sha256,
            "legacy_ruleset_sha256": self.legacy_ruleset_sha256,
            "effective_ruleset_sha256": self.effective_ruleset_sha256,
            "legacy_model_sha256": self.legacy_model_sha256,
            "effective_model_sha256": self.effective_model_sha256,
            "legacy_output_sha256": self.legacy_output_sha256,
            "effective_output_sha256": self.effective_output_sha256,
            "fiscal_delta": self.fiscal_delta,
            "input_or_model_delta": self.input_or_model_delta,
            "baseline_generation_id": str(self.baseline_generation_id)
            if self.baseline_generation_id
            else None,
            "preimage_row_count": len(self.preimage_rows),
            "legacy_row_count": len(self.legacy_rows),
            "effective_row_count": len(self.effective_rows),
            "effective_apply": "BLOCKED",
        }


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
    if isinstance(value, float):
        return repr(value)
    return value


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        _canonical_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def scope_payload(scopes: Sequence[Scope]) -> list[dict[str, str]]:
    return [
        {"company_name": company, "period": period.isoformat()}
        for company, period in scopes
    ]


def normalize_scopes(scopes: Iterable[Scope], input_cutoff: date) -> tuple[Scope, ...]:
    if input_cutoff.day != 1:
        raise ShadowGenerationError("Input cutoff trebuie sa fie prima zi din luna.")
    normalized = tuple(sorted({(company.strip(), period) for company, period in scopes}))
    if not normalized:
        raise ShadowGenerationError("Este necesar cel putin un scope company:YYYY-MM.")
    for company, period in normalized:
        if company not in {"Mobicell", "Mobiup"} or period.day != 1:
            raise ShadowGenerationError("Scope-ul trebuie sa fie (company, prima zi din luna).")
        if period > input_cutoff:
            raise ShadowGenerationError("Scope-ul nu poate depasi input cutoff-ul fix.")
    return normalized


def _estimate_payload(row: estimator.Estimate) -> dict[str, Any]:
    return {
        "company_name": row.company_name,
        "period": row.period,
        "site_code": row.site_code,
        "source_site_code": row.source_site_code,
        "source_location_name": row.source_location_name,
        "category_code": row.category_code,
        "category_name": row.category_name,
        "amount": row.amount,
    }


def _sorted_payload_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    payload = [_canonical_value(dict(row)) for row in rows]
    return sorted(payload, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))


def output_sha256(rows: Iterable[estimator.Estimate]) -> str:
    return canonical_sha256(_sorted_payload_rows(_estimate_payload(row) for row in rows))


def _model_sha256(version: str) -> str:
    source = Path(estimator.__file__).read_bytes()
    return hashlib.sha256(version.encode("utf-8") + b"\0" + source).hexdigest()


def _legacy_ruleset_sha256() -> str:
    return canonical_sha256(
        {
            "ruleset_id": LEGACY_VAT_RULESET_ID,
            "rules": [{"multiplier": "1.19", "effective_from": "0001-01-01"}],
        }
    )


def _row_key(row: estimator.Estimate) -> tuple[str, date, str, str]:
    return row.company_name, row.period, row.site_code, row.category_code


def _decimal(value: Decimal | int | float | str | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def summarize_delta(
    before: Iterable[estimator.Estimate],
    after: Iterable[estimator.Estimate],
    *,
    basis: str,
) -> dict[str, Any]:
    left = {_row_key(row): _decimal(row.amount) for row in before}
    right = {_row_key(row): _decimal(row.amount) for row in after}
    by_scope: dict[tuple[str, date], dict[str, Any]] = {}
    changed = 0
    for key in sorted(set(left) | set(right)):
        old, new = left.get(key, Decimal("0.00")), right.get(key, Decimal("0.00"))
        if old == new:
            continue
        changed += 1
        company, period, _, _ = key
        bucket = by_scope.setdefault(
            (company, period),
            {
                "company_name": company,
                "period": period.isoformat(),
                "before_total": Decimal("0.00"),
                "after_total": Decimal("0.00"),
                "delta": Decimal("0.00"),
                "changed_row_count": 0,
            },
        )
        bucket["before_total"] += old
        bucket["after_total"] += new
        bucket["delta"] += new - old
        bucket["changed_row_count"] += 1
    return {
        "available": True,
        "basis": basis,
        "before_total": format(sum(left.values(), Decimal("0.00")), "f"),
        "after_total": format(sum(right.values(), Decimal("0.00")), "f"),
        "total_delta": format(sum(right.values(), Decimal("0.00")) - sum(left.values(), Decimal("0.00")), "f"),
        "changed_row_count": changed,
        "by_scope": [
            {
                **bucket,
                "before_total": format(bucket["before_total"], "f"),
                "after_total": format(bucket["after_total"], "f"),
                "delta": format(bucket["delta"], "f"),
            }
            for _, bucket in sorted(by_scope.items())
        ],
    }


async def _fetch_preimage(
    connection: asyncpg.Connection,
    scopes: Sequence[Scope],
) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for company, period in scopes:
        result = await connection.fetch(
            """
            SELECT company_name, period, source_site_code, source_location_name,
                   category_code, category_name, amount, data_kind, source_file,
                   source_sha256
            FROM store_pnl_monthly
            WHERE company_name = $1 AND period = $2
            ORDER BY source_site_code, category_code, data_kind
            """,
            company,
            period,
        )
        rows.extend(dict(row) for row in result)
    return tuple(
        sorted(
            rows,
            key=lambda row: json.dumps(
                _canonical_value(row), sort_keys=True, separators=(",", ":")
            ),
        )
    )


def _shadow_targets(
    sales_rows: Iterable[Mapping[str, Any]],
    scopes: Sequence[Scope],
) -> set[tuple[str, date, str]]:
    selected = set(scopes)
    return {
        (row["company_name"], row["period"], row["site_code"])
        for row in sales_rows
        if (row["company_name"], row["period"]) in selected
        and _decimal(row["amount"]) > 0
    }


async def _baseline_legacy_rows(
    connection: asyncpg.Connection,
    baseline_generation_id: UUID | None,
    scope_sha256: str,
) -> tuple[estimator.Estimate, ...] | None:
    if baseline_generation_id is None:
        return None
    generation = await connection.fetchrow(
        """
        SELECT scope_sha256 FROM store_pnl_shadow_generations WHERE id = $1
        """,
        baseline_generation_id,
    )
    if generation is None:
        raise ShadowGenerationError("Baseline generation nu exista.")
    if generation["scope_sha256"] != scope_sha256:
        raise ShadowGenerationError("Baseline generation are alt scope; comparatia ar fi invalida.")
    rows = await connection.fetch(
        """
        SELECT company_name, period, site_code, source_site_code,
               source_location_name, category_code, category_name, amount
        FROM store_pnl_shadow_rows
        WHERE generation_id = $1 AND variant = 'legacy_v2'
        ORDER BY company_name, period, site_code, category_code
        """,
        baseline_generation_id,
    )
    return tuple(
        estimator.Estimate(
            row["company_name"], row["period"], row["site_code"],
            row["source_site_code"], row["source_location_name"],
            row["category_code"], row["category_name"], row["amount"],
        )
        for row in rows
    )


async def capture_shadow(
    connection: asyncpg.Connection,
    scopes: Iterable[Scope],
    input_cutoff: date,
    *,
    baseline_generation_id: UUID | None = None,
) -> ShadowCapture:
    """Capture both candidates from a read-only repeatable-read snapshot."""
    normalized_scopes = normalize_scopes(scopes, input_cutoff)
    scope_hash = canonical_sha256(scope_payload(normalized_scopes))
    async with connection.transaction(isolation="repeatable_read", readonly=True):
        actual, gross_sales, salaries, stores = await estimator.load_inputs(
            connection,
            input_cutoff=input_cutoff,
        )
        preimage = await _fetch_preimage(connection, normalized_scopes)
        legacy_sales = estimator.normalize_sales(gross_sales, effective_vat=False)
        effective_sales = estimator.normalize_sales(gross_sales, effective_vat=True)
        targets = _shadow_targets(legacy_sales, normalized_scopes)
        legacy_rows = tuple(
            estimator.build_estimates(
                actual, legacy_sales, salaries, stores, targets,
                causal=False, include_actual_targets=True,
            )
        )
        effective_rows = tuple(
            estimator.build_estimates(
                actual, effective_sales, salaries, stores, targets,
                causal=False, include_actual_targets=True,
            )
        )
        baseline_rows = await _baseline_legacy_rows(
            connection,
            baseline_generation_id,
            scope_hash,
        )
        input_payload = {
            "scope": scope_payload(normalized_scopes),
            "input_cutoff": input_cutoff,
            "actual": _sorted_payload_rows(dict(row) for row in actual),
            "gross_sales": _sorted_payload_rows(dict(row) for row in gross_sales),
            "salaries": _sorted_payload_rows(dict(row) for row in salaries),
            "stores": _sorted_payload_rows(dict(row) for row in stores),
        }
    if baseline_rows is None:
        input_or_model_delta: dict[str, Any] = {
            "available": False,
            "reason": "Nu exista baseline legacy-v2 cu acelasi scope pentru izolarea driftului.",
        }
    else:
        input_or_model_delta = summarize_delta(
            baseline_rows,
            legacy_rows,
            basis="current_legacy_v2_minus_baseline_legacy_v2",
        )
        input_or_model_delta["baseline_generation_id"] = str(baseline_generation_id)
    return ShadowCapture(
        scopes=normalized_scopes,
        input_cutoff=input_cutoff,
        source_sha256=canonical_sha256(preimage),
        input_sha256=canonical_sha256(input_payload),
        legacy_ruleset_sha256=_legacy_ruleset_sha256(),
        effective_ruleset_sha256=standard_vat_ruleset_hash(),
        legacy_model_sha256=_model_sha256(estimator.LEGACY_MODEL_VERSION),
        effective_model_sha256=_model_sha256(estimator.EFFECTIVE_MODEL_VERSION),
        legacy_output_sha256=output_sha256(legacy_rows),
        effective_output_sha256=output_sha256(effective_rows),
        fiscal_delta=summarize_delta(
            legacy_rows,
            effective_rows,
            basis="effective_v3_minus_legacy_v2_same_snapshot",
        ),
        input_or_model_delta=input_or_model_delta,
        baseline_generation_id=baseline_generation_id,
        preimage_rows=preimage,
        legacy_rows=legacy_rows,
        effective_rows=effective_rows,
    )


async def stage_shadow_capture(
    connection: asyncpg.Connection,
    capture: ShadowCapture,
) -> UUID:
    """Persist only review/provenance tables; never writes store_pnl_monthly."""
    generation_id = uuid4()
    async with connection.transaction():
        await connection.execute(
            """
            INSERT INTO store_pnl_shadow_generations (
                id, scope, scope_sha256, input_cutoff, source_sha256, input_sha256,
                legacy_ruleset_sha256, effective_ruleset_sha256,
                legacy_model_sha256, effective_model_sha256,
                legacy_output_sha256, effective_output_sha256,
                fiscal_delta, input_or_model_delta, baseline_generation_id
            ) VALUES (
                $1,$2::jsonb,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb,$14::jsonb,$15
            )
            """,
            generation_id,
            json.dumps(scope_payload(capture.scopes), sort_keys=True),
            capture.scope_sha256,
            capture.input_cutoff,
            capture.source_sha256,
            capture.input_sha256,
            capture.legacy_ruleset_sha256,
            capture.effective_ruleset_sha256,
            capture.legacy_model_sha256,
            capture.effective_model_sha256,
            capture.legacy_output_sha256,
            capture.effective_output_sha256,
            json.dumps(capture.fiscal_delta, sort_keys=True),
            json.dumps(capture.input_or_model_delta, sort_keys=True),
            capture.baseline_generation_id,
        )
        shadow_values = [
            (
                generation_id, variant, row.company_name, row.period, row.site_code,
                row.source_site_code, row.source_location_name, row.category_code,
                row.category_name, row.amount,
            )
            for variant, rows in (
                ("legacy_v2", capture.legacy_rows),
                ("effective_v3", capture.effective_rows),
            )
            for row in rows
        ]
        if shadow_values:
            await connection.executemany(
                """
                INSERT INTO store_pnl_shadow_rows (
                    generation_id, variant, company_name, period, site_code,
                    source_site_code, source_location_name, category_code,
                    category_name, amount
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                """,
                shadow_values,
            )
        if capture.preimage_rows:
            await connection.executemany(
                """
                INSERT INTO store_pnl_shadow_preimage_rows (
                    generation_id, company_name, period, source_site_code,
                    source_location_name, category_code, category_name, amount,
                    data_kind, source_file, source_sha256
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                """,
                [
                    (
                        generation_id, row["company_name"], row["period"],
                        row["source_site_code"], row["source_location_name"],
                        row["category_code"], row["category_name"], row["amount"],
                        row["data_kind"], row["source_file"], row["source_sha256"],
                    )
                    for row in capture.preimage_rows
                ],
            )
        await connection.fetchval(
            "SELECT seal_store_pnl_shadow_generation($1)",
            generation_id,
        )
    return generation_id


async def promote_shadow_generation(
    connection: asyncpg.Connection,
    generation_id: UUID,
    *,
    expected_revision: int,
) -> int:
    """CAS-update the review pointer; runtime P&L remains untouched."""
    async with connection.transaction():
        try:
            revision = await connection.fetchval(
                "SELECT promote_store_pnl_shadow_generation($1, $2)",
                generation_id,
                expected_revision,
            )
        except asyncpg.PostgresError as exc:
            if "pointer revision changed" in str(exc):
                raise PointerRevisionMismatch(
                    "Revision shadow concurenta; promovarea a fost refuzata."
                ) from None
            raise ShadowGenerationError(
                "Generatia shadow nu poate fi promovata; sealul, starea sau digestul nu corespund."
            ) from None
    if revision is None:
        raise ShadowGenerationError("Promovarea shadow nu a returnat o revizie.")
    return int(revision)


async def rollback_shadow_pointer(
    connection: asyncpg.Connection,
    *,
    expected_revision: int,
) -> int:
    """CAS-rollback to the immediately prior review generation, exactly once."""
    async with connection.transaction():
        try:
            revision = await connection.fetchval(
                "SELECT rollback_store_pnl_shadow_pointer($1)",
                expected_revision,
            )
        except asyncpg.PostgresError as exc:
            if "pointer revision changed" in str(exc):
                raise PointerRevisionMismatch(
                    "Revision shadow concurenta; rollbackul a fost refuzat."
                ) from None
            raise ShadowGenerationError(
                "Pointerul shadow nu are un predecessor valid pentru rollback."
            ) from None
    if revision is None:
        raise ShadowGenerationError("Rollbackul shadow nu a returnat o revizie.")
    return int(revision)


def apply_effective_generation(*_args: Any, **_kwargs: Any) -> None:
    """This release has no route from shadow rows to live P&L rows."""
    raise EffectivePromotionBlocked(
        "Apply effective TVA este blocat; shadow pointer-ul nu modifica store_pnl_monthly."
    )
