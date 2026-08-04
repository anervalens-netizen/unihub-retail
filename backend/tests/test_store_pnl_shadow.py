"""P0.3 shadow provenance: deterministic Decimal math and isolated CAS state."""
from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest

from db.connection import get_pool
from scripts import estimate_store_pnl as estimator
from services.fiscal_rules import gross_to_net, legacy_gross_to_net
from services.store_pnl_shadow import (
    EffectivePromotionBlocked,
    PointerRevisionMismatch,
    ShadowCapture,
    canonical_sha256,
    capture_shadow,
    promote_shadow_generation,
    rollback_shadow_pointer,
    stage_shadow_capture,
    summarize_delta,
)


PERIOD = date(2098, 7, 1)
COMPANY = "Mobiup"


def _estimate(amount: str, *, category: str = "v1") -> estimator.Estimate:
    return estimator.Estimate(
        COMPANY,
        PERIOD,
        "SHADOW-SITE",
        "SHADOW-SITE",
        "Shadow test",
        category,
        category,
        Decimal(amount),
    )


def _capture() -> ShadowCapture:
    return ShadowCapture(
        scopes=((COMPANY, PERIOD),),
        input_cutoff=PERIOD,
        source_sha256="a" * 64,
        input_sha256="b" * 64,
        legacy_ruleset_sha256="c" * 64,
        effective_ruleset_sha256="d" * 64,
        legacy_model_sha256="e" * 64,
        effective_model_sha256="f" * 64,
        legacy_output_sha256="1" * 64,
        effective_output_sha256="2" * 64,
        fiscal_delta={"available": True, "total_delta": "1.00"},
        input_or_model_delta={"available": False},
        baseline_generation_id=None,
        preimage_rows=(
            {
                "company_name": COMPANY,
                "period": PERIOD,
                "source_site_code": "SHADOW-SITE",
                "source_location_name": "Shadow test",
                "category_code": "v1",
                "category_name": "Revenue",
                "amount": Decimal("119.00"),
                "data_kind": "actual",
                "source_file": "shadow-test.xlsx",
                "source_sha256": "3" * 64,
            },
        ),
        legacy_rows=(_estimate("100.00"),),
        effective_rows=(_estimate("101.00"),),
    )


def test_effective_normalization_matches_fiscal_helper_to_cent() -> None:
    gross = Decimal("121.00")
    source = [{"company_name": COMPANY, "period": PERIOD, "site_code": "S", "gross_amount": gross}]

    assert estimator.normalize_sales(source, effective_vat=True)[0]["amount"] == gross_to_net(gross, PERIOD)
    assert estimator.normalize_sales(source, effective_vat=False)[0]["amount"] == legacy_gross_to_net(gross, PERIOD)
    assert estimator.predict_amount(
        "c11",
        date(2098, 8, 1),
        [(date(2098, 5, 1), Decimal("10.00")), (date(2098, 6, 1), Decimal("20.00"))],
        {date(2098, 5, 1): Decimal("100.00"), date(2098, 6, 1): Decimal("200.00")},
        {},
        Decimal("300.00"),
        Decimal("0.00"),
    ) == Decimal("30.00")

    reference = date(2098, 6, 1)
    actual = [
        {
            "company_name": COMPANY,
            "period": reference,
            "source_site_code": "REFERENCE",
            "source_location_name": "Reference",
            "site_code": "REFERENCE",
            "category_code": category,
            "category_name": estimator.CATEGORY_NAMES[category],
            "amount": Decimal("10.00"),
        }
        for category in estimator.CATEGORY_NAMES
    ]
    sales = estimator.normalize_sales(
        [
            {"company_name": COMPANY, "period": reference, "site_code": "REFERENCE", "gross_amount": Decimal("119.00")},
            {"company_name": COMPANY, "period": PERIOD, "site_code": "MISSING", "gross_amount": gross},
        ],
        effective_vat=True,
    )
    estimates = estimator.build_estimates(
        actual,
        sales,
        [],
        [
            {"site_code": "REFERENCE", "locatie": "Reference", "firma": "Mobiup"},
            {"site_code": "MISSING", "locatie": "Missing", "firma": "Mobiup"},
        ],
        {(COMPANY, PERIOD, "MISSING")},
        causal=False,
    )
    assert sum(
        (row.amount for row in estimates if row.category_code in estimator.REVENUE_CODES),
        Decimal("0.00"),
    ) == gross_to_net(gross, PERIOD)


def test_hash_and_delta_are_deterministic_without_float_rounding() -> None:
    assert canonical_sha256({"amount": Decimal("1.10"), "period": PERIOD}) == canonical_sha256(
        {"period": PERIOD, "amount": Decimal("1.10")}
    )
    delta = summarize_delta((_estimate("100.00"),), (_estimate("101.01"),), basis="test")
    assert delta["total_delta"] == "1.01"
    assert delta["changed_row_count"] == 1


@pytest.mark.anyio
async def test_effective_apply_is_hard_blocked_before_database_connection() -> None:
    with pytest.raises(RuntimeError, match="este blocata"):
        await estimator.run([], True, effective_vat=True)
    with pytest.raises(EffectivePromotionBlocked):
        from services.store_pnl_shadow import apply_effective_generation

        apply_effective_generation()


class _Transaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_args: object) -> None:
        return None


class _SnapshotConnection:
    def __init__(self) -> None:
        self.transaction_kwargs: dict[str, object] | None = None

    def transaction(self, **kwargs: object) -> _Transaction:
        self.transaction_kwargs = kwargs
        return _Transaction()

    async def fetch(self, _query: str, *_args: object) -> list[dict[str, object]]:
        return []


@pytest.mark.anyio
async def test_capture_uses_readonly_repeatable_read_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_inputs(_connection: object, *, input_cutoff: date):
        assert input_cutoff == PERIOD
        return [], [], [], []

    monkeypatch.setattr(estimator, "load_inputs", fake_inputs)
    connection = _SnapshotConnection()
    capture = await capture_shadow(connection, [(COMPANY, PERIOD)], PERIOD)  # type: ignore[arg-type]

    assert connection.transaction_kwargs == {"isolation": "repeatable_read", "readonly": True}
    assert capture.input_or_model_delta["available"] is False
    assert capture.report()["effective_apply"] == "BLOCKED"


requires_isolated_db = pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated test database",
)


async def _reset() -> None:
    pool = await get_pool()
    async with pool.acquire() as connection:
        triggers = (
            ("store_pnl_shadow_pointer", "trg_store_pnl_shadow_pointer_cas"),
            ("store_pnl_shadow_generations", "trg_store_pnl_shadow_generations_immutable"),
            ("store_pnl_shadow_rows", "trg_store_pnl_shadow_rows_immutable"),
            ("store_pnl_shadow_preimage_rows", "trg_store_pnl_shadow_preimage_rows_immutable"),
        )
        for table, trigger in triggers:
            await connection.execute(f"ALTER TABLE {table} DISABLE TRIGGER {trigger}")
        try:
            await connection.execute(
                """
                UPDATE store_pnl_shadow_pointer
                SET active_generation_id = NULL, previous_generation_id = NULL, revision = 0
                WHERE id = 1
                """
            )
            await connection.execute(
                "DELETE FROM store_pnl_shadow_generations WHERE scope_sha256 = $1",
                _capture().scope_sha256,
            )
        finally:
            for table, trigger in reversed(triggers):
                await connection.execute(f"ALTER TABLE {table} ENABLE TRIGGER {trigger}")
        await connection.execute(
            "DELETE FROM store_pnl_monthly WHERE company_name = $1 AND period = $2",
            COMPANY,
            PERIOD,
        )


@pytest.mark.anyio
@requires_isolated_db
async def test_stage_and_pointer_cas_never_mutate_live_pnl() -> None:
    await _reset()
    pool = await get_pool()
    capture = _capture()
    try:
        async with pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO store_pnl_monthly (
                    company_name, period, source_site_code, source_location_name,
                    category_code, category_name, amount, data_kind, source_file, source_sha256
                ) VALUES ($1,$2,'SHADOW-SITE','Shadow test','v1','Revenue',119.00,'actual',$3,$4)
                """,
                COMPANY,
                PERIOD,
                "shadow-test.xlsx",
                "3" * 64,
            )
            original = await connection.fetchval(
                "SELECT amount FROM store_pnl_monthly WHERE company_name = $1 AND period = $2",
                COMPANY,
                PERIOD,
            )
            first = await stage_shadow_capture(connection, capture)
            second = await stage_shadow_capture(connection, capture)
            third = await stage_shadow_capture(connection, capture)
            assert await connection.fetchval(
                "SELECT amount FROM store_pnl_monthly WHERE company_name = $1 AND period = $2",
                COMPANY,
                PERIOD,
            ) == original == Decimal("119.00")

            assert await promote_shadow_generation(connection, first, expected_revision=0) == 1
            with pytest.raises(PointerRevisionMismatch):
                await promote_shadow_generation(connection, second, expected_revision=0)
            assert await promote_shadow_generation(connection, second, expected_revision=1) == 2
            assert await rollback_shadow_pointer(connection, expected_revision=2) == 3
            pointer = await connection.fetchrow(
                "SELECT active_generation_id, previous_generation_id, revision FROM store_pnl_shadow_pointer WHERE id = 1"
            )
            assert pointer["active_generation_id"] == first
            assert pointer["previous_generation_id"] is None
            assert pointer["revision"] == 3
            assert await connection.fetchval(
                "SELECT state FROM store_pnl_shadow_generations WHERE id = $1",
                second,
            ) == "rolled_back"
            assert await connection.fetchval(
                "SELECT state FROM store_pnl_shadow_generations WHERE id = $1",
                third,
            ) == "staged"
    finally:
        await _reset()
