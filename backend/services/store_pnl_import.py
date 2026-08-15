"""Immutable, Finance-authorized staging and promotion for monthly P&L.

The CLI owns workbook parsing; this module owns the authority-manifest,
generation-manifest, database fencing, and inverse rollback contracts.  It
deliberately has no fallback to a filename, workbook density, or ``DATABASE_URL``.
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import asyncpg

from db.connection import verify_database_connection_authority
from services.store_pnl_contract import (
    CENT,
    COMPANIES,
    HEX64,
    AuthorityManifest,
    AuthorityScope,
    PnlBusinessKey,
    PnlGenerationConflict,
    PnlImportError,
    PnlRow,
    PnlScope,
    StageResult,
    _canonical_value,
    _cutoff,
    _digest_scalar,
    _is_sha256,
    _month,
    _relative_source_path,
    _row_digest_payload,
    business_key,
    canonical_sha256,
    coverage_regressions,
    coverage_sha256,
    ensure_unique_business_keys,
    normalized_rows,
    row_payload,
    rows_sha256,
    scope_totals,
    validate_scope_candidate,
)


def _parse_authority_scope(raw: object) -> AuthorityScope:
    if not isinstance(raw, Mapping):
        raise PnlImportError("Fiecare authority scope trebuie sa fie obiect.")
    company = raw.get("company_name")
    if company not in COMPANIES:
        raise PnlImportError("company_name Finance este invalid.")
    period = _month(raw.get("period"), field="period")
    cutoff = _cutoff(raw.get("cutoff"))
    if cutoff < period:
        raise PnlImportError("cutoff nu poate preceda luna Finance.")
    revision_id = raw.get("revision_id")
    parent_revision_id = raw.get("parent_revision_id")
    if not isinstance(revision_id, str) or not revision_id.strip():
        raise PnlImportError("revision_id lipseste din authority manifest.")
    if not isinstance(parent_revision_id, str) or not parent_revision_id.strip():
        raise PnlImportError("parent_revision_id lipseste din authority manifest.")
    if not _is_sha256(raw.get("source_sha256")):
        raise PnlImportError("source_sha256 trebuie sa fie SHA-256 lowercase.")
    if raw.get("complete_snapshot") is not True:
        raise PnlImportError("Authority scope necesita complete_snapshot=true.")
    row_count = raw.get("expected_row_count")
    if not isinstance(row_count, int) or isinstance(row_count, bool) or row_count <= 0:
        raise PnlImportError("expected_row_count trebuie sa fie int pozitiv.")
    try:
        expected_total = Decimal(str(raw.get("expected_total_amount"))).quantize(CENT)
    except Exception as exc:  # Decimal exposes several concrete errors.
        raise PnlImportError("expected_total_amount este invalid.") from exc
    if not expected_total.is_finite():
        raise PnlImportError("expected_total_amount trebuie sa fie finit.")
    if not _is_sha256(raw.get("coverage_sha256")):
        raise PnlImportError("coverage_sha256 trebuie sa fie SHA-256 lowercase.")
    return AuthorityScope(
        company_name=company,
        period=period,
        revision_id=revision_id.strip(),
        parent_revision_id=parent_revision_id.strip(),
        cutoff=cutoff,
        source_path=_relative_source_path(raw.get("source_path")),
        source_sha256=raw["source_sha256"],
        expected_row_count=row_count,
        expected_total_amount=expected_total,
        coverage_sha256=raw["coverage_sha256"],
    )


def parse_authority_manifest(payload: object) -> AuthorityManifest:
    if not isinstance(payload, Mapping):
        raise PnlImportError("Authority manifest trebuie sa fie un obiect JSON.")
    if payload.get("version") != 1:
        raise PnlImportError("Authority manifest version trebuie sa fie 1.")
    approval_id = payload.get("approval_id")
    if not isinstance(approval_id, str) or not approval_id.strip():
        raise PnlImportError("Authority manifest necesita approval_id extern.")
    raw_scopes = payload.get("scopes")
    if not isinstance(raw_scopes, list) or not raw_scopes:
        raise PnlImportError("Authority manifest necesita scopes nevid.")
    scopes: list[AuthorityScope] = []
    seen: set[PnlScope] = set()
    for raw in raw_scopes:
        scope = _parse_authority_scope(raw)
        if scope.key in seen:
            raise PnlImportError("Authority manifest are scope Finance duplicat.")
        seen.add(scope.key)
        scopes.append(scope)
    canonical_payload = _canonical_value(dict(payload))
    return AuthorityManifest(
        version=1,
        approval_id=approval_id.strip(),
        scopes=tuple(sorted(scopes, key=lambda item: item.key)),
        sha256=canonical_sha256(canonical_payload),
        payload=canonical_payload,
    )




def _record_to_row(record: Mapping[str, Any]) -> PnlRow:
    return PnlRow(
        company_name=record["company_name"],
        period=record["period"],
        source_site_code=record["source_site_code"],
        source_location_name=record["source_location_name"],
        category_code=record["category_code"],
        category_name=record["category_name"],
        amount=Decimal(record["amount"]),
        source_file=record["source_file"],
        source_sha256=record["source_sha256"],
    )


async def _actual_rows(connection: asyncpg.Connection, scope: PnlScope) -> list[PnlRow]:
    company, period = scope
    records = await connection.fetch(
        """
        SELECT company_name, period, source_site_code, source_location_name,
               category_code, category_name, amount, source_file, source_sha256
        FROM store_pnl_monthly
        WHERE company_name = $1 AND period = $2 AND data_kind = 'actual'
        ORDER BY source_site_code, category_code
        """,
        company,
        period,
    )
    return [_record_to_row(record) for record in records]


async def _head(connection: asyncpg.Connection, scope: PnlScope) -> Mapping[str, Any] | None:
    company, period = scope
    return await connection.fetchrow(
        """
        SELECT company_name, period, active_generation_id, revision, revision_id
        FROM store_pnl_generation_heads
        WHERE company_name = $1 AND period = $2
        """,
        company,
        period,
    )


async def _lock_scope(connection: asyncpg.Connection, scope: PnlScope) -> None:
    company, period = scope
    await connection.execute(
        "SELECT pg_advisory_xact_lock(hashtext($1), hashtext($2))",
        "store_pnl_generation",
        f"{company}:{period.isoformat()}",
    )


def _scope_generation_manifest(
    scope: AuthorityScope,
    candidate_rows: Sequence[PnlRow],
    preimage_rows: Sequence[PnlRow],
    expected_head_revision: int,
) -> dict[str, Any]:
    candidate_count, candidate_total = scope_totals(candidate_rows)
    removed = coverage_regressions(preimage_rows, candidate_rows)
    return {
        "company_name": scope.company_name,
        "period": scope.period,
        "revision_id": scope.revision_id,
        "parent_revision_id": scope.parent_revision_id,
        "cutoff": scope.cutoff,
        "source_path": scope.source_path,
        "source_sha256": scope.source_sha256,
        "candidate_rows_sha256": rows_sha256(candidate_rows),
        "candidate_coverage_sha256": coverage_sha256(candidate_rows),
        "candidate_row_count": candidate_count,
        "candidate_total_amount": candidate_total,
        "preimage_sha256": rows_sha256(preimage_rows),
        "removed_business_key_count": len(removed),
        "removed_business_keys_sha256": canonical_sha256(removed),
        "expected_head_revision": expected_head_revision,
    }


async def _require_finance_import_role(connection: asyncpg.Connection) -> None:
    try:
        await verify_database_connection_authority(connection, "finance_import")
    except RuntimeError as exc:
        raise PnlImportError(
            "Importul P&L necesita principalul autentificat Finance dedicat."
        ) from exc


def _validate_staging_authority(authority: AuthorityManifest) -> None:
    try:
        canonical_authority = parse_authority_manifest(authority.payload)
    except PnlImportError as exc:
        raise PnlImportError(
            "Authority manifest nu mai corespunde payloadului validat."
        ) from exc
    if canonical_authority != authority:
        raise PnlImportError("Authority manifest nu mai corespunde payloadului validat.")
    if {scope.company_name for scope in authority.scopes} != COMPANIES:
        raise PnlImportError(
            "Stagingul Finance necesita batch reconciliat pentru ambele companii."
        )


async def stage_generation(
    connection: asyncpg.Connection,
    authority: AuthorityManifest,
    candidates: Mapping[PnlScope, Sequence[PnlRow]],
) -> StageResult:
    _validate_staging_authority(authority)
    await _require_finance_import_role(connection)
    if set(candidates) != {scope.key for scope in authority.scopes}:
        raise PnlImportError("Candidatele si authority manifest nu au exact aceleasi scope-uri.")
    generation_id = uuid4()
    staged_scopes: list[dict[str, Any]] = []
    preimages: dict[PnlScope, list[PnlRow]] = {}
    async with connection.transaction():
        for scope in authority.scopes:
            candidate_rows = list(candidates[scope.key])
            validate_scope_candidate(scope, candidate_rows)
            preimage = await _actual_rows(connection, scope.key)
            head = await _head(connection, scope.key)
            if head is None:
                if scope.parent_revision_id != "legacy":
                    raise PnlGenerationConflict("Primul staging Finance necesita parent_revision_id=legacy.")
                expected_head_revision = 0
            else:
                if scope.parent_revision_id != head["revision_id"]:
                    raise PnlGenerationConflict("parent_revision_id nu corespunde headului Finance curent.")
                expected_head_revision = int(head["revision"])
            preimages[scope.key] = preimage
            staged_scopes.append(
                _scope_generation_manifest(scope, candidate_rows, preimage, expected_head_revision)
            )

        generation_manifest = {
            "version": 1,
            "operation": "promote",
            "generation_id": generation_id,
            "authority_manifest_sha256": authority.sha256,
            "approval_id": authority.approval_id,
            "scopes": staged_scopes,
        }
        manifest_sha256 = canonical_sha256(generation_manifest)
        await connection.execute(
            """
            INSERT INTO store_pnl_generations (
                id, operation, authority_manifest_sha256, authority_manifest,
                generation_manifest_sha256, generation_manifest, state
            ) VALUES ($1, 'promote', $2, $3::jsonb, $4, $5::jsonb, 'building')
            """,
            generation_id,
            authority.sha256,
            json.dumps(authority.payload, sort_keys=True),
            manifest_sha256,
            json.dumps(_canonical_value(generation_manifest), sort_keys=True),
        )
        for scope_manifest, authority_scope in zip(staged_scopes, authority.scopes, strict=True):
            await connection.execute(
                """
                INSERT INTO store_pnl_generation_scopes (
                    generation_id, company_name, period, revision_id, parent_revision_id,
                    cutoff, source_path, source_sha256, candidate_rows_sha256,
                    candidate_coverage_sha256, candidate_row_count, candidate_total_amount,
                    preimage_sha256, expected_head_revision
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                """,
                generation_id,
                authority_scope.company_name,
                authority_scope.period,
                authority_scope.revision_id,
                authority_scope.parent_revision_id,
                authority_scope.cutoff,
                authority_scope.source_path,
                authority_scope.source_sha256,
                scope_manifest["candidate_rows_sha256"],
                scope_manifest["candidate_coverage_sha256"],
                scope_manifest["candidate_row_count"],
                scope_manifest["candidate_total_amount"],
                scope_manifest["preimage_sha256"],
                scope_manifest["expected_head_revision"],
            )
            candidate_values = [
                (generation_id, "candidate", *row_payload(row).values())
                for row in candidates[authority_scope.key]
            ]
            if candidate_values:
                await connection.executemany(
                    """
                    INSERT INTO store_pnl_generation_rows (
                        generation_id, row_set, company_name, period, source_site_code,
                        source_location_name, category_code, category_name, amount,
                        source_file, source_sha256
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                    """,
                    candidate_values,
                )
            preimage_values = [
                (generation_id, "preimage", *row_payload(row).values())
                for row in preimages[authority_scope.key]
            ]
            if preimage_values:
                await connection.executemany(
                    """
                    INSERT INTO store_pnl_generation_rows (
                        generation_id, row_set, company_name, period, source_site_code,
                        source_location_name, category_code, category_name, amount,
                        source_file, source_sha256
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                    """,
                    preimage_values,
                )
        await connection.fetchval(
            "SELECT stage_store_pnl_generation($1, $2)",
            generation_id,
            manifest_sha256,
        )
    return StageResult(generation_id, manifest_sha256, generation_manifest)


async def _generation_rows(
    connection: asyncpg.Connection,
    generation_id: UUID,
    row_set: str,
    scope: PnlScope,
) -> list[PnlRow]:
    company, period = scope
    records = await connection.fetch(
        """
        SELECT company_name, period, source_site_code, source_location_name,
               category_code, category_name, amount, source_file, source_sha256
        FROM store_pnl_generation_rows
        WHERE generation_id = $1 AND row_set = $2 AND company_name = $3 AND period = $4
        ORDER BY source_site_code, category_code
        """,
        generation_id,
        row_set,
        company,
        period,
    )
    return [_record_to_row(record) for record in records]


async def _promote_staged_generation(
    connection: asyncpg.Connection,
    generation_id: UUID,
    expected_manifest_sha256: str,
) -> dict[str, int]:
    generation = await connection.fetchrow(
        """
        SELECT state, generation_manifest_sha256
        FROM store_pnl_generations WHERE id = $1
        """,
        generation_id,
    )
    if generation is None:
        raise PnlImportError("Generatia P&L nu exista.")
    if generation["state"] != "staged":
        raise PnlGenerationConflict("Poate fi promovată numai o generatie P&L staged.")
    if generation["generation_manifest_sha256"] != expected_manifest_sha256:
        raise PnlGenerationConflict("expected-manifest-sha nu corespunde generatiei staged.")
    try:
        revisions = await connection.fetchval(
            "SELECT promote_store_pnl_generation($1, $2)",
            generation_id,
            expected_manifest_sha256,
        )
    except asyncpg.PostgresError:
        raise PnlGenerationConflict(
            "Promovarea Finance controlata DB a refuzat generatia sau CAS-ul."
        ) from None
    if isinstance(revisions, str):
        revisions = json.loads(revisions)
    if not isinstance(revisions, dict):
        raise PnlGenerationConflict("Promovarea Finance nu a returnat reviziile CAS.")
    return {str(key): int(value) for key, value in revisions.items()}


async def apply_generation(
    connection: asyncpg.Connection,
    generation_id: UUID,
    expected_manifest_sha256: str,
) -> dict[str, int]:
    if not _is_sha256(expected_manifest_sha256):
        raise PnlImportError("expected-manifest-sha trebuie sa fie SHA-256 lowercase.")
    await _require_finance_import_role(connection)
    async with connection.transaction():
        return await _promote_staged_generation(connection, generation_id, expected_manifest_sha256)


async def rollback_generation(
    connection: asyncpg.Connection,
    source_generation_id: UUID,
    expected_manifest_sha256: str,
) -> StageResult:
    """Publish a new inverse generation; never move a P&L head backwards."""
    if not _is_sha256(expected_manifest_sha256):
        raise PnlImportError("expected-manifest-sha trebuie sa fie SHA-256 lowercase.")
    await _require_finance_import_role(connection)
    inverse_id = uuid4()
    async with connection.transaction():
        source = await connection.fetchrow(
            """
            SELECT generation_manifest_sha256, state
            FROM store_pnl_generations WHERE id = $1
            """,
            source_generation_id,
        )
        if source is None or source["state"] != "promoted":
            raise PnlGenerationConflict("Rollbackul necesita generatie P&L promovata.")
        if source["generation_manifest_sha256"] != expected_manifest_sha256:
            raise PnlGenerationConflict("expected-manifest-sha nu corespunde generatiei de rollback.")
        source_scopes = await connection.fetch(
            """
            SELECT company_name, period, revision_id, cutoff, source_path, source_sha256
            FROM store_pnl_generation_scopes WHERE generation_id = $1
            ORDER BY company_name, period
            """,
            source_generation_id,
        )
        if {scope["company_name"] for scope in source_scopes} != COMPANIES:
            raise PnlImportError("Rollbackul Finance necesita batch pentru ambele companii.")
        inverse_scope_manifests: list[dict[str, Any]] = []
        inverse_rows: dict[PnlScope, list[PnlRow]] = {}
        current_rows: dict[PnlScope, list[PnlRow]] = {}
        for source_scope in source_scopes:
            key = (source_scope["company_name"], source_scope["period"])
            await _lock_scope(connection, key)
            head = await _head(connection, key)
            if head is None or head["active_generation_id"] != source_generation_id:
                raise PnlGenerationConflict("Headul P&L nu mai indica generatia ceruta pentru rollback.")
            current = await _actual_rows(connection, key)
            original = await _generation_rows(connection, source_generation_id, "preimage", key)
            inverse_rows[key] = original
            current_rows[key] = current
            candidate_count, candidate_total = scope_totals(original)
            inverse_scope_manifests.append(
                {
                    "company_name": key[0], "period": key[1],
                    "revision_id": f"rollback:{source_generation_id}",
                    "parent_revision_id": source_scope["revision_id"],
                    "cutoff": source_scope["cutoff"],
                    "source_path": source_scope["source_path"],
                    "source_sha256": source_scope["source_sha256"],
                    "candidate_rows_sha256": rows_sha256(original),
                    "candidate_coverage_sha256": coverage_sha256(original),
                    "candidate_row_count": candidate_count,
                    "candidate_total_amount": candidate_total,
                    "preimage_sha256": rows_sha256(current),
                    "expected_head_revision": int(head["revision"]),
                }
            )
        inverse_manifest = {
            "version": 1,
            "operation": "rollback",
            "generation_id": inverse_id,
            "source_generation_id": source_generation_id,
            "source_generation_manifest_sha256": expected_manifest_sha256,
            "scopes": inverse_scope_manifests,
        }
        inverse_sha = canonical_sha256(inverse_manifest)
        await connection.execute(
            """
            INSERT INTO store_pnl_generations (
                id, operation, authority_manifest_sha256, authority_manifest,
                generation_manifest_sha256, generation_manifest, state, inverse_of_generation_id
            ) VALUES ($1, 'rollback', $2, $3::jsonb, $4, $5::jsonb, 'building', $6)
            """,
            inverse_id, expected_manifest_sha256,
            json.dumps({"operation": "rollback", "source_generation_id": str(source_generation_id)}, sort_keys=True),
            inverse_sha, json.dumps(_canonical_value(inverse_manifest), sort_keys=True), source_generation_id,
        )
        for scope_manifest in inverse_scope_manifests:
            key = (scope_manifest["company_name"], scope_manifest["period"])
            await connection.execute(
                """
                INSERT INTO store_pnl_generation_scopes (
                    generation_id, company_name, period, revision_id, parent_revision_id,
                    cutoff, source_path, source_sha256, candidate_rows_sha256,
                    candidate_coverage_sha256, candidate_row_count, candidate_total_amount,
                    preimage_sha256, expected_head_revision
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                """,
                inverse_id, key[0], key[1], scope_manifest["revision_id"],
                scope_manifest["parent_revision_id"], scope_manifest["cutoff"],
                scope_manifest["source_path"], scope_manifest["source_sha256"],
                scope_manifest["candidate_rows_sha256"], scope_manifest["candidate_coverage_sha256"],
                scope_manifest["candidate_row_count"], scope_manifest["candidate_total_amount"],
                scope_manifest["preimage_sha256"], scope_manifest["expected_head_revision"],
            )
            for row_set, rows in (("candidate", inverse_rows[key]), ("preimage", current_rows[key])):
                if rows:
                    await connection.executemany(
                        """
                        INSERT INTO store_pnl_generation_rows (
                            generation_id, row_set, company_name, period, source_site_code,
                            source_location_name, category_code, category_name, amount,
                            source_file, source_sha256
                        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                        """,
                        [(inverse_id, row_set, *row_payload(row).values()) for row in rows],
                    )
        await connection.fetchval(
            "SELECT stage_store_pnl_generation($1, $2)",
            inverse_id,
            inverse_sha,
        )
        await _promote_staged_generation(connection, inverse_id, inverse_sha)
    return StageResult(inverse_id, inverse_sha, inverse_manifest)
