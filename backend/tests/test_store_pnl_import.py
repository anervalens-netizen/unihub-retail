from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from scripts.import_store_pnl import (
    UNALLOCATED_SOURCE,
    WorkbookData,
    build_parser,
    detail_category,
    materialize_authority_rows,
    merged_rows,
    unallocated_rows,
)
from services.store_pnl_import import (
    PnlImportError,
    PnlRow,
    _scope_generation_manifest,
    _replace_actual_scope,
    apply_generation,
    canonical_sha256,
    coverage_regressions,
    coverage_sha256,
    parse_authority_manifest,
    rows_sha256,
    stage_generation,
    validate_scope_candidate,
)


PERIOD = date(2026, 7, 1)
SHA_A = "a" * 64
SHA_B = "b" * 64


def row(
    *,
    company: str = "Mobiup",
    source_file: str = "approved.xls",
    source_sha256: str = SHA_A,
    site: str = "SITE",
    category: str = "v1",
    amount: str = "100.00",
) -> PnlRow:
    return PnlRow(
        company, PERIOD, site, "Magazin", category, "Venit", Decimal(amount), source_file, source_sha256
    )


def authority(rows: list[PnlRow], *, revision: str = "r2", parent: str = "legacy"):
    assert rows
    first = rows[0]
    payload = {
        "version": 1,
        "approval_id": "FIN-2026-07-approved",
        "scopes": [{
            "company_name": first.company_name,
            "period": first.period.isoformat(),
            "revision_id": revision,
            "parent_revision_id": parent,
            "cutoff": "2026-07-31",
            "source_path": first.source_file,
            "source_sha256": first.source_sha256,
            "complete_snapshot": True,
            "expected_row_count": len(rows),
            "expected_total_amount": str(sum((item.amount for item in rows), Decimal("0.00"))),
            "coverage_sha256": coverage_sha256(rows),
        }],
    }
    return parse_authority_manifest(payload)


def workbook(
    rows: list[PnlRow],
    *,
    source_file: str = "approved.xls",
    source_sha256: str = SHA_A,
    consolidated: list[PnlRow] | None = None,
) -> WorkbookData:
    return WorkbookData(
        Path(source_file), source_file, source_sha256, rows[0].company_name if rows else "Mobiup",
        (PERIOD,), tuple(rows), tuple(consolidated or ()),
    )


def test_detail_category_recovers_shifted_finance_rows() -> None:
    sheet = MagicMock()
    sheet.cell_value.side_effect = lambda _row, column: {1: "", 5: "c11-ACM"}.get(column, "")
    assert detail_category(sheet, 421) == "c11"


def test_authority_hash_is_recomputable_from_exact_persisted_payload() -> None:
    manifest = authority([row()])
    assert manifest.payload["scopes"][0]["complete_snapshot"] is True
    assert canonical_sha256(manifest.payload) == manifest.sha256


def test_candidate_rejects_row_from_undeclared_source_even_when_business_key_matches() -> None:
    manifest = authority([row()])
    foreign = row(source_file="foreign.xls")
    with pytest.raises(PnlImportError, match="exact.*sursa authority"):
        validate_scope_candidate(manifest.scopes[0], [foreign])


def test_authority_and_candidate_reject_non_finite_money() -> None:
    payload = authority([row()]).payload
    payload["scopes"][0]["expected_total_amount"] = "NaN"
    with pytest.raises(PnlImportError, match="finit"):
        parse_authority_manifest(payload)

    manifest = authority([row()])
    with pytest.raises(PnlImportError, match="finite"):
        validate_scope_candidate(manifest.scopes[0], [row(amount="NaN")])


def test_authority_requires_exact_sources_and_rejects_source_rename() -> None:
    approved = row()
    manifest = authority([approved])
    renamed = workbook([row(source_file="renamed.xls")], source_file="renamed.xls")
    with pytest.raises(PnlImportError, match="Sursele observate"):
        materialize_authority_rows([renamed], manifest)


def test_authority_rejects_mutated_and_undeclared_bundle() -> None:
    approved = row()
    manifest = authority([approved])
    changed = workbook([row(source_sha256=SHA_B)], source_sha256=SHA_B)
    extra = workbook([row(source_file="extra.xls", source_sha256=SHA_B)], source_file="extra.xls", source_sha256=SHA_B)
    with pytest.raises(PnlImportError, match="Sursele observate"):
        materialize_authority_rows([changed], manifest)
    with pytest.raises(PnlImportError, match="Sursele observate"):
        materialize_authority_rows([workbook([approved]), extra], manifest)


def test_same_business_key_changed_amount_changes_generation_hash() -> None:
    original = row(amount="100.00")
    correction = row(amount="101.00")
    assert rows_sha256([original]) != rows_sha256([correction])


def test_complete_snapshot_records_removed_keys_instead_of_using_coverage_heuristic() -> None:
    old = row(category="c1", amount="10.00")
    candidate = row(category="v1", amount="100.00")
    manifest = authority([candidate])
    scope_manifest = _scope_generation_manifest(manifest.scopes[0], [candidate], [old], 4)
    assert coverage_regressions([old], [candidate]) == [("Mobiup", PERIOD, "SITE", "c1")]
    assert scope_manifest["removed_business_key_count"] == 1


def test_unallocated_delta_cannot_mix_a_second_workbook() -> None:
    detail = row(amount="90.00")
    total = row(site=UNALLOCATED_SOURCE, amount="100.00")
    source = workbook([detail], consolidated=[total])
    delta = unallocated_rows([detail], source, ("Mobiup", PERIOD))
    assert len(delta) == 1
    assert delta[0].amount == Decimal("10.00")
    assert delta[0].source_file == "approved.xls"


def test_materialize_rejects_unapproved_month_from_same_source() -> None:
    approved = row()
    manifest = authority([approved])
    unexpected = PnlRow("Mobiup", date(2026, 8, 1), "SITE", "Magazin", "v1", "Venit", Decimal("1.00"), "approved.xls", SHA_A)
    with pytest.raises(PnlImportError, match="luni neaprobate"):
        materialize_authority_rows([workbook([approved, unexpected])], manifest)


def test_stage_requires_both_finance_companies_before_database_access() -> None:
    manifest = authority([row()])
    connection = MagicMock()
    with pytest.raises(PnlImportError, match="ambele companii"):
        __import__("asyncio").run(stage_generation(connection, manifest, {manifest.scopes[0].key: [row()]}))
    assert not connection.fetchval.called


def test_stage_revalidates_authority_payload_and_hash_before_database_access() -> None:
    manifest = replace(authority([row()]), sha256=SHA_B)
    connection = MagicMock()
    with pytest.raises(PnlImportError, match="nu mai corespunde payloadului"):
        __import__("asyncio").run(
            stage_generation(connection, manifest, {manifest.scopes[0].key: [row()]})
        )
    assert not connection.fetchval.called


@pytest.mark.anyio
async def test_apply_rejects_runtime_database_role_before_transaction() -> None:
    connection = MagicMock()
    connection.fetchval = AsyncMock(return_value="unihub_runtime")
    with pytest.raises(PnlImportError, match="unihub_finance_import"):
        await apply_generation(connection, uuid4(), SHA_A)
    assert not connection.transaction.called


@pytest.mark.anyio
async def test_replace_actual_scope_never_deletes_or_inserts_estimates() -> None:
    connection = MagicMock()
    connection.execute = AsyncMock()
    connection.executemany = AsyncMock()
    await _replace_actual_scope(connection, ("Mobiup", PERIOD), [row()])
    delete_sql = connection.execute.await_args.args[0]
    insert_sql = connection.executemany.await_args.args[0]
    assert "data_kind = 'actual'" in delete_sql
    assert "estimated" not in delete_sql
    assert "'actual'" in insert_sql


def test_legacy_apply_flag_is_not_an_interface() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--apply"])


def test_merged_rows_preserves_single_source_and_sums_accounting_lines() -> None:
    first = row(amount="1.00")
    second = row(amount="2.00")
    merged = merged_rows([first, second])
    assert len(merged) == 1
    assert merged[0].amount == Decimal("3.00")
