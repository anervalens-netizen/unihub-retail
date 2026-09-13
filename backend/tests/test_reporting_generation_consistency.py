"""Lot 45: composed sales-derived reads must come from one sales generation.

The composed results covered here are:

  * ``AiForecastService.get_current`` - latest run selection, reporting cutoff,
    aggregate actuals, expected-to-date and the daily series.
  * the Export report/artifact compositions - total rows, monthly rows and
    daily rows of one artifact, and the per-level daily-comparison tables.

Every database test runs against a real isolated PostgreSQL and drives a real
sales-generation promotion: a validated staged generation (migration 037),
the CAS head, the append-only promotions ledger and rebuilt reporting
aggregates (migration 040). No integrity control is disabled and the epoch is
never mocked to an integer.

The interleaving harness commits the promotion on its own connection at a
deterministic statement boundary, which is exactly the hazard PostgreSQL READ
COMMITTED exposes when a composition reuses one connection across statements.
"""

from __future__ import annotations

import asyncio
import os
from calendar import monthrange
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import asyncpg
import pytest
from fastapi import HTTPException

from repositories.ai_forecast import AiForecastRepository
from repositories.exports import ExportsRepository
from routers.ai_forecast import get_current_ai_forecast
from routers.exports import ExportRequest, preview_export
from services.ai_forecast import AiForecastService
from services.exports import ExportsService, ExportValidationError
from services.reporting_consistency import (
    ReportingGenerationUnstable,
    load_reporting_result_once_stable,
)


requires_postgres = pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated PostgreSQL",
)

SITE = "L45S1"
GENERATION_A: dict[str, Any] = {
    "cutoff_day": 10, "filename": "lot45-a.xlsx", "value": "1000.00", "qty": 10,
}
GENERATION_B: dict[str, Any] = {
    "cutoff_day": 20, "filename": "lot45-b.xlsx", "value": "2000.00", "qty": 20,
}


# ---------------------------------------------------------------------------
# Deterministic statement-boundary interleaving over a REAL asyncpg pool
# ---------------------------------------------------------------------------


class _Hook:
    """Fires a real promotion at most ``limit`` times on matching statements."""

    def __init__(self, match: Any, promote: Any, *, limit: int = 1, when: str = "after") -> None:
        assert when in {"before", "after"}
        self.match = match
        self.promote = promote
        self.limit = limit
        self.when = when
        self.fired = 0

    async def before(self, sql: str) -> None:
        if self.when == "before":
            await self._maybe(sql)

    async def after(self, sql: str) -> None:
        if self.when == "after":
            await self._maybe(sql)

    async def _maybe(self, sql: str) -> None:
        if self.fired >= self.limit or not self.match(sql):
            return
        self.fired += 1
        await self.promote()


class _ProxyConnection:
    """Delegating connection that reports every statement to its owning pool."""

    def __init__(self, conn: Any, owner: "ObservedPool") -> None:
        self._conn = conn
        self._owner = owner

    async def _before(self, sql: str) -> None:
        self._owner.statements.append(sql)
        if self._owner.hook is not None:
            await self._owner.hook.before(sql)

    async def _after(self, sql: str) -> None:
        if self._owner.hook is not None:
            await self._owner.hook.after(sql)

    async def fetchval(self, sql: str, *params: Any) -> Any:
        await self._before(sql)
        value = await self._conn.fetchval(sql, *params)
        await self._after(sql)
        return value

    async def fetchrow(self, sql: str, *params: Any) -> Any:
        await self._before(sql)
        value = await self._conn.fetchrow(sql, *params)
        await self._after(sql)
        return value

    async def fetch(self, sql: str, *params: Any) -> Any:
        await self._before(sql)
        value = await self._conn.fetch(sql, *params)
        await self._after(sql)
        return value

    async def execute(self, sql: str, *params: Any) -> Any:
        await self._before(sql)
        value = await self._conn.execute(sql, *params)
        await self._after(sql)
        return value

    def transaction(self, *args: Any, **kwargs: Any) -> Any:
        if self._owner.forbid_transaction:
            raise AssertionError("a fenced reporting read opened a DB transaction")
        return self._conn.transaction(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


class _Acquire:
    def __init__(self, owner: "ObservedPool") -> None:
        self._owner = owner
        self._acquire: Any = None

    async def __aenter__(self) -> _ProxyConnection:
        self._acquire = self._owner.pool.acquire()
        conn = await self._acquire.__aenter__()
        return _ProxyConnection(conn, self._owner)

    async def __aexit__(self, *exc: object) -> bool:
        return await self._acquire.__aexit__(*exc)


class ObservedPool:
    """Real pool whose statements are recorded and optionally interleaved."""

    def __init__(
        self,
        pool: Any,
        hook: _Hook | None = None,
        *,
        forbid_transaction: bool = False,
    ) -> None:
        self.pool = pool
        self.hook = hook
        self.statements: list[str] = []
        self.forbid_transaction = forbid_transaction

    def acquire(self) -> _Acquire:
        return _Acquire(self)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.pool, name)


# ---------------------------------------------------------------------------
# Real promotion fixture
# ---------------------------------------------------------------------------

_MONTH_SEQUENCE = iter(range(0, 240))


def next_month() -> str:
    """A fresh month per test: the promotions ledger is append-only."""
    index = next(_MONTH_SEQUENCE)
    return f"{2998 + index // 12}-{index % 12 + 1:02d}"


async def _create_generation(
    conn: Any,
    *,
    month: str,
    generation: dict[str, Any],
    revision: int,
    previous_snapshot_id: int | None,
) -> int:
    """Build one validated staged generation and move the CAS head onto it."""
    cutoff = date.fromisoformat(f"{month}-{generation['cutoff_day']:02d}")
    snapshot_id = int(
        await conn.fetchval(
            "INSERT INTO import_snapshots (import_month, filename, upload_date, status, "
            "cutoff_date, previous_snapshot_id) "
            "VALUES ($1, $2, CURRENT_DATE, 'processing', $3, $4) RETURNING id",
            month, generation["filename"], cutoff, previous_snapshot_id,
        )
    )
    await conn.execute(
        "INSERT INTO sales_import_stage_rows (snapshot_id, row_number, import_month, sale_date, "
        "site_code, locatie, firma, regional, asm, bon_nr, item_code, item_name, quantity, "
        "unit_price, total_value, agent, is_cartela, is_return) "
        "VALUES ($1, 1, $2, $3, $4, 'Lot45 Store', 'Firma A', 'Regional 1', 'ASM 1', "
        "'B1', 'I1', 'Item 1', 1, 10.00, 10.00, 'Agent 1', false, false)",
        snapshot_id, month, cutoff, SITE,
    )
    await conn.execute(
        "UPDATE import_snapshots SET status = 'completed', "
        "stage_rows_sha256 = sales_stage_rows_sha256(id), "
        "manifest = jsonb_build_object('stage_rows_sha256', sales_stage_rows_sha256(id), "
        "'generation_state', 'promoted') WHERE id = $1",
        snapshot_id,
    )
    await conn.execute(
        "INSERT INTO sales_generation_heads (import_month, snapshot_id, revision) "
        "VALUES ($1, $2, $3) ON CONFLICT (import_month) DO UPDATE "
        "SET snapshot_id = EXCLUDED.snapshot_id, revision = EXCLUDED.revision, updated_at = now()",
        month, snapshot_id, revision,
    )
    await conn.execute(
        "INSERT INTO sales_generation_promotions (import_month, from_snapshot_id, "
        "to_snapshot_id, head_revision, action, requested_by_sub) "
        "VALUES ($1, $2, $3, $4, 'promote', 'lot45:test')",
        month, previous_snapshot_id, snapshot_id, revision,
    )
    return snapshot_id


async def _rebuild_reporting_aggregates(conn: Any, month: str, generation: dict[str, Any]) -> None:
    """Rebuild the sales-derived read models a promotion would replace."""
    await conn.execute(
        "DELETE FROM reporting_agent_day WHERE import_month = $1 AND site_code = $2",
        month, SITE,
    )
    await conn.execute(
        "DELETE FROM reporting_agent_month WHERE import_month = $1 AND site_code = $2",
        month, SITE,
    )
    await conn.execute(
        "INSERT INTO reporting_agent_month (import_month, site_code, locatie, firma, regional, "
        "asm, agent, total_sales, total_quantity) VALUES ($1, $2, 'Lot45 Store', 'Firma A', "
        "'Regional 1', 'ASM 1', 'Agent 1', $3, $4)",
        month, SITE, generation["value"], generation["qty"],
    )
    await conn.execute(
        "INSERT INTO reporting_agent_day (import_month, sale_date, site_code, locatie, firma, "
        "regional, asm, agent, total_sales, total_quantity) VALUES ($1, $2, $3, 'Lot45 Store', "
        "'Firma A', 'Regional 1', 'ASM 1', 'Agent 1', $4, $5)",
        month, date.fromisoformat(f"{month}-{generation['cutoff_day']:02d}"), SITE,
        generation["value"], generation["qty"],
    )


async def promote_generation(url: str, month: str, generation: dict[str, Any]) -> None:
    """Commit one real promotion, including its rebuilt reporting aggregates."""
    conn = await asyncpg.connect(url)
    try:
        async with conn.transaction():
            previous = await conn.fetchval(
                "SELECT snapshot_id FROM sales_generation_heads WHERE import_month = $1", month
            )
            revision = await conn.fetchval(
                "SELECT revision FROM sales_generation_heads WHERE import_month = $1", month
            )
            await _create_generation(
                conn, month=month, generation=generation,
                revision=int(revision) + 1, previous_snapshot_id=int(previous),
            )
            await _rebuild_reporting_aggregates(conn, month, generation)
    finally:
        await conn.close()


async def seed_generation_a(url: str, month: str, *, forecast_run: bool) -> None:
    """Materialise generation A, optionally with a current-month forecast run."""
    conn = await asyncpg.connect(url)
    try:
        await conn.execute(
            "INSERT INTO stores (site_code, locatie, firma, regional, asm, first_seen_month, "
            "last_seen_month) VALUES ($1, 'Lot45 Store', 'Firma A', 'Regional 1', 'ASM 1', "
            "'2026-01', $2) ON CONFLICT (site_code) DO UPDATE SET locatie = EXCLUDED.locatie",
            SITE, month,
        )
        await _create_generation(
            conn, month=month, generation=GENERATION_A, revision=1, previous_snapshot_id=None
        )
        await _rebuild_reporting_aggregates(conn, month, GENERATION_A)
        if not forecast_run:
            return
        year, month_number = (int(part) for part in month.split("-"))
        run_id = await conn.fetchval(
            "INSERT INTO ai_forecast_runs (forecast_month, source_month, metric, horizon, "
            "model_name, model_mode, variant, status, generated_at) "
            "VALUES ($1, '2997-12', 'sales_value', 'current_month', 'lot45', 'auto', 'v1', "
            "'completed', now()) RETURNING id",
            month,
        )
        await conn.execute(
            "INSERT INTO ai_forecast_store_month (run_id, site_code, forecast_sales) "
            "VALUES ($1, $2, 5000.00)",
            run_id, SITE,
        )
        for day in range(1, monthrange(year, month_number)[1] + 1):
            await conn.execute(
                "INSERT INTO ai_forecast_store_day (run_id, forecast_date, site_code, "
                "forecast_sales) VALUES ($1, $2, $3, 100.00)",
                run_id, date.fromisoformat(f"{month}-{day:02d}"), SITE,
            )
    finally:
        await conn.close()


async def seed_rolling_run(url: str, month: str) -> None:
    """Add one rolling-12m run so the single-statement rolling read executes."""
    conn = await asyncpg.connect(url)
    try:
        year, month_number = (int(part) for part in month.split("-"))
        month_index = year * 12 + (month_number - 1) + 1
        target = f"{month_index // 12:04d}-{month_index % 12 + 1:02d}"
        run_id = await conn.fetchval(
            "INSERT INTO ai_forecast_runs (forecast_month, source_month, metric, horizon, "
            "model_name, model_mode, variant, status, generated_at, metadata) "
            "VALUES ($1, $2::TEXT, 'sales_value', 'rolling_12m', 'lot45', 'auto', 'v1', "
            "'completed', now(), jsonb_build_object('anchor_month', $3::TEXT)) RETURNING id",
            target, month, month,
        )
        await conn.execute(
            "INSERT INTO ai_forecast_store_month (run_id, site_code, forecast_sales) "
            "VALUES ($1, $2, 5000.00)",
            run_id, SITE,
        )
    finally:
        await conn.close()


async def _pool(url: str, **kwargs: Any) -> Any:
    return await asyncpg.create_pool(url, min_size=1, max_size=4, **kwargs)


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is required for the isolated regression")
    return url


def forecast_request(month: str) -> dict[str, Any]:
    return {
        "month": month, "metric": "sales_value",
        "firma": None, "regional": None, "asm": None, "site_code": None,
    }


def export_request(month: str) -> dict[str, Any]:
    return {
        "dataset": "stores",
        "months": [month],
        "dimensions": ["site_code"],
        "metrics": ["total_sales"],
        "monthly_metrics": ["total_sales"],
        "daily_metrics": ["total_sales"],
        "selected_days": list(range(1, 32)),
        "filters": {},
        "include_closed_stores": False,
    }


def export_columns(result: dict[str, Any]) -> tuple[str, str, str]:
    keys = [column["key"] for column in result["columns"]]
    month_key = next(key for key in keys if key.startswith("month:"))
    day_key = next(key for key in keys if key.startswith("day:"))
    return "total_sales", month_key, day_key


def export_values(result: dict[str, Any]) -> tuple[Decimal, Decimal, Decimal]:
    row = result["rows"][0]
    total_key, month_key, day_key = export_columns(result)
    return (
        Decimal(str(row[total_key])),
        Decimal(str(row[month_key])),
        Decimal(str(row[day_key])),
    )


# ---------------------------------------------------------------------------
# The hazard is real: unfenced compositions still mix generations
# ---------------------------------------------------------------------------


@requires_postgres
@pytest.mark.asyncio
async def test_unfenced_forecast_load_mixes_cutoff_with_actuals() -> None:
    """Baseline boundary: the unfenced loader mixes cutoff A with actuals B."""
    url = database_url()
    month = next_month()
    await seed_generation_a(url, month, forecast_run=True)
    pool = await _pool(url)
    try:
        hook = _Hook(
            lambda sql: "FROM reporting_sales_cutoff_v1" in sql,
            lambda: promote_generation(url, month, GENERATION_B),
        )
        service = AiForecastService(AiForecastRepository(ObservedPool(pool, hook)))
        response = await service._load_current(**forecast_request(month))

        assert hook.fired == 1
        assert response is not None
        assert response.summary.days_elapsed == GENERATION_A["cutoff_day"]
        assert str(response.summary.actual_sales) == GENERATION_B["value"]
    finally:
        await pool.close()


@requires_postgres
@pytest.mark.asyncio
async def test_unfenced_export_report_mixes_total_with_period_columns() -> None:
    """Baseline boundary: total rows come from A while month/day come from B."""
    url = database_url()
    month = next_month()
    await seed_generation_a(url, month, forecast_run=False)
    pool = await _pool(url)
    try:
        hook = _Hook(
            _is_export_total_read,
            lambda: promote_generation(url, month, GENERATION_B),
        )
        service = ExportsService(ExportsRepository(ObservedPool(pool, hook)))
        plan = service._report_plan(export_request(month))
        loaded = await service._load_report(plan, row_limit=1000, preview_limit=None)
        result, _ = service._finalize_report(plan, loaded.rows, loaded.total_records, None)

        assert hook.fired == 1
        total, monthly, daily = export_values(result)
        assert total == Decimal(GENERATION_A["value"])
        assert monthly == Decimal(GENERATION_B["value"])
        assert daily == Decimal(GENERATION_B["value"])
    finally:
        await pool.close()


def _is_export_total_read(sql: str) -> bool:
    """The un-periodised total read that runs before every per-period read."""
    return (
        "agg.period_key AS period_key" in sql
        and "NULL::TEXT AS period_key" in sql
        and "agg.import_month AS period_key" not in sql
        and "agg.sale_date::TEXT AS period_key" not in sql
    )


# ---------------------------------------------------------------------------
# AI Forecast
# ---------------------------------------------------------------------------


def _forecast_is_consistent(response: Any) -> bool:
    cutoff_day = response.summary.days_elapsed
    actual = str(response.summary.actual_sales)
    nonzero = [
        index + 1
        for index, point in enumerate(response.daily)
        if Decimal(str(point.actual_sales)) != 0
    ]
    if cutoff_day == GENERATION_A["cutoff_day"]:
        return actual == GENERATION_A["value"] and nonzero == [GENERATION_A["cutoff_day"]]
    if cutoff_day == GENERATION_B["cutoff_day"]:
        return actual == GENERATION_B["value"] and nonzero == [GENERATION_B["cutoff_day"]]
    return False


@requires_postgres
@pytest.mark.asyncio
async def test_forecast_stable_generation_is_read_once() -> None:
    url = database_url()
    month = next_month()
    await seed_generation_a(url, month, forecast_run=True)
    pool = await _pool(url)
    try:
        observed = ObservedPool(pool)
        service = AiForecastService(AiForecastRepository(observed))
        response = await service.get_current(**forecast_request(month))

        assert response is not None
        assert response.summary.days_elapsed == GENERATION_A["cutoff_day"]
        assert str(response.summary.actual_sales) == GENERATION_A["value"]
        assert _forecast_is_consistent(response)
        assert observed.statements.count("SELECT public.current_sales_generation_epoch()") == 2
    finally:
        await pool.close()


@requires_postgres
@pytest.mark.asyncio
async def test_forecast_discards_mixed_attempt_and_returns_generation_b() -> None:
    url = database_url()
    month = next_month()
    await seed_generation_a(url, month, forecast_run=True)
    pool = await _pool(url)
    try:
        hook = _Hook(
            lambda sql: "FROM reporting_sales_cutoff_v1" in sql,
            lambda: promote_generation(url, month, GENERATION_B),
        )
        service = AiForecastService(AiForecastRepository(ObservedPool(pool, hook)))
        response = await service.get_current(**forecast_request(month))

        assert hook.fired == 1
        assert response is not None
        assert response.summary.days_elapsed == GENERATION_B["cutoff_day"]
        assert str(response.summary.actual_sales) == GENERATION_B["value"]
        assert _forecast_is_consistent(response)
    finally:
        await pool.close()


@requires_postgres
@pytest.mark.asyncio
async def test_forecast_refuses_when_every_attempt_is_unstable() -> None:
    url = database_url()
    month = next_month()
    await seed_generation_a(url, month, forecast_run=True)
    pool = await _pool(url)
    try:
        hook = _Hook(
            lambda sql: "FROM reporting_sales_cutoff_v1" in sql,
            lambda: promote_generation(url, month, GENERATION_B),
            limit=2,
        )
        service = AiForecastService(AiForecastRepository(ObservedPool(pool, hook)))
        with pytest.raises(ReportingGenerationUnstable):
            await service.get_current(**forecast_request(month))
        assert hook.fired == 2
    finally:
        await pool.close()


def test_forecast_router_maps_instability_to_503() -> None:
    async def unstable(**_kwargs: Any) -> Any:
        raise ReportingGenerationUnstable()

    svc = cast(Any, SimpleNamespace(get_current=unstable))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            get_current_ai_forecast(
                month="2026-05", metric="sales_value", firma=None, regional=None,
                asm=None, site_code=None, svc=svc,
            )
        )

    assert exc.value.status_code == 503
    assert isinstance(exc.value.detail, str)


def test_forecast_router_keeps_404_semantics() -> None:
    async def missing(**_kwargs: Any) -> None:
        return None

    svc = cast(Any, SimpleNamespace(get_current=missing))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            get_current_ai_forecast(
                month="2026-05", metric="sales_value", firma=None, regional=None,
                asm=None, site_code=None, svc=svc,
            )
        )

    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------


@requires_postgres
@pytest.mark.asyncio
async def test_export_report_stable_generation_is_read_once() -> None:
    url = database_url()
    month = next_month()
    await seed_generation_a(url, month, forecast_run=False)
    pool = await _pool(url)
    try:
        service = ExportsService(ExportsRepository(ObservedPool(pool)))
        result = await service.build_report(export_request(month))

        total, monthly, daily = export_values(result)
        assert total == monthly == daily == Decimal(GENERATION_A["value"])
    finally:
        await pool.close()


@requires_postgres
@pytest.mark.asyncio
async def test_export_report_rebuilds_every_column_after_generation_change() -> None:
    url = database_url()
    month = next_month()
    await seed_generation_a(url, month, forecast_run=False)
    pool = await _pool(url)
    try:
        hook = _Hook(
            _is_export_total_read,
            lambda: promote_generation(url, month, GENERATION_B),
        )
        service = ExportsService(ExportsRepository(ObservedPool(pool, hook)))
        result = await service.build_report(export_request(month))

        assert hook.fired == 1
        total, monthly, daily = export_values(result)
        assert total == monthly == daily == Decimal(GENERATION_B["value"])
    finally:
        await pool.close()


@requires_postgres
@pytest.mark.asyncio
async def test_export_report_refuses_when_every_attempt_is_unstable() -> None:
    url = database_url()
    month = next_month()
    await seed_generation_a(url, month, forecast_run=False)
    pool = await _pool(url)
    try:
        hook = _Hook(
            _is_export_total_read,
            lambda: promote_generation(url, month, GENERATION_B),
            limit=2,
        )
        service = ExportsService(ExportsRepository(ObservedPool(pool, hook)))
        with pytest.raises(ReportingGenerationUnstable):
            await service.build_report(export_request(month))
        assert hook.fired == 2
    finally:
        await pool.close()


@requires_postgres
@pytest.mark.asyncio
async def test_export_preview_is_fenced_and_never_mixes_generations() -> None:
    url = database_url()
    month = next_month()
    await seed_generation_a(url, month, forecast_run=False)
    pool = await _pool(url)
    try:
        hook = _Hook(
            _is_export_total_read,
            lambda: promote_generation(url, month, GENERATION_B),
        )
        service = ExportsService(ExportsRepository(ObservedPool(pool, hook)))
        request = export_request(month) | {"preview_limit": 5}
        result = await service.preview(request)

        row = result["rows"][0]
        assert hook.fired == 1
        assert Decimal(str(row["total_sales"])) == Decimal(GENERATION_B["value"])
        month_key = next(key for key in row if key.startswith("month:"))
        day_key = next(key for key in row if key.startswith("day:"))
        assert Decimal(str(row[month_key])) == Decimal(GENERATION_B["value"])
        assert Decimal(str(row[day_key])) == Decimal(GENERATION_B["value"])
    finally:
        await pool.close()


@requires_postgres
@pytest.mark.asyncio
async def test_export_artifact_fences_report_and_daily_evolution_together() -> None:
    """The XLSX path reads the report and the daily evolution under one fence."""
    url = database_url()
    month = next_month()
    await seed_generation_a(url, month, forecast_run=False)
    pool = await _pool(url)
    try:
        hook = _Hook(
            _is_export_total_read,
            lambda: promote_generation(url, month, GENERATION_B),
        )
        service = ExportsService(ExportsRepository(ObservedPool(pool, hook)))
        request = export_request(month) | {"export_mode": "table", "preview_limit": 5}
        artifact = await service.build_xlsx_artifact(request)
        try:
            assert hook.fired == 1
            assert artifact.size > 0
        finally:
            artifact.close()
    finally:
        await pool.close()


@requires_postgres
@pytest.mark.asyncio
async def test_export_daily_comparison_levels_share_one_generation() -> None:
    url = database_url()
    month = next_month()
    await seed_generation_a(url, month, forecast_run=False)
    pool = await _pool(url)
    try:
        hook = _Hook(
            lambda sql: "day_of_month" in sql,
            lambda: promote_generation(url, month, GENERATION_B),
        )
        service = ExportsService(ExportsRepository(ObservedPool(pool, hook)))
        request = {
            "export_mode": "daily_comparison",
            "comparison_levels": ["general", "stores"],
            "months": [month],
            "metrics": ["total_sales"],
            "selected_days": list(range(1, 32)),
            "filters": {},
            "include_closed_stores": False,
        }
        artifact = await service.build_xlsx_artifact(request)
        try:
            assert hook.fired == 1
            assert artifact.size > 0
        finally:
            artifact.close()
    finally:
        await pool.close()


def test_export_preview_router_maps_instability_to_503() -> None:
    async def unstable(_request: dict[str, Any]) -> Any:
        raise ReportingGenerationUnstable()

    svc = cast(Any, SimpleNamespace(preview=unstable))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            preview_export(body=_export_request_body(), _rate_limit=None, svc=svc)
        )

    assert exc.value.status_code == 503
    assert isinstance(exc.value.detail, str)


def test_export_preview_router_keeps_400_semantics() -> None:
    async def invalid(_request: dict[str, Any]) -> Any:
        raise ExportValidationError("Dataset invalid.")

    svc = cast(Any, SimpleNamespace(preview=invalid))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            preview_export(body=_export_request_body(), _rate_limit=None, svc=svc)
        )

    assert exc.value.status_code == 400


def _export_request_body() -> Any:
    return ExportRequest(dataset="stores", months=["2026-05"])


# ---------------------------------------------------------------------------
# Retry mechanics, cancellation and resource cleanup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fence_accepts_the_first_stable_attempt() -> None:
    epochs = iter([4, 4])
    loads: list[int] = []

    async def read_epoch() -> int:
        return next(epochs)

    async def load() -> str:
        loads.append(1)
        return "A"

    result = await load_reporting_result_once_stable(
        read_epoch=read_epoch, load=load, operation="unit"
    )

    assert result == "A"
    assert len(loads) == 1


@pytest.mark.asyncio
async def test_fence_discards_the_first_attempt_and_retries_once() -> None:
    epochs = iter([4, 5, 5, 5])
    attempts: list[str] = []

    async def read_epoch() -> int:
        return next(epochs)

    async def load() -> str:
        attempts.append(f"attempt-{len(attempts) + 1}")
        return attempts[-1]

    result = await load_reporting_result_once_stable(
        read_epoch=read_epoch, load=load, operation="unit"
    )

    assert result == "attempt-2"
    assert attempts == ["attempt-1", "attempt-2"]


@pytest.mark.asyncio
async def test_fence_refuses_after_two_unstable_attempts() -> None:
    epochs = iter([4, 5, 5, 6])
    loads: list[int] = []

    async def read_epoch() -> int:
        return next(epochs)

    async def load() -> str:
        loads.append(1)
        return "value"

    with pytest.raises(ReportingGenerationUnstable):
        await load_reporting_result_once_stable(
            read_epoch=read_epoch, load=load, operation="unit"
        )

    assert len(loads) == 2


@pytest.mark.asyncio
async def test_fence_never_retries_a_raising_load() -> None:
    epochs = iter([4])
    loads: list[int] = []

    async def read_epoch() -> int:
        return next(epochs)

    async def load() -> str:
        loads.append(1)
        raise ExportValidationError("boom")

    with pytest.raises(ExportValidationError):
        await load_reporting_result_once_stable(
            read_epoch=read_epoch, load=load, operation="unit"
        )

    assert len(loads) == 1


@pytest.mark.asyncio
async def test_fence_propagates_cancellation_without_retrying() -> None:
    started = asyncio.Event()
    loads: list[int] = []

    async def read_epoch() -> int:
        return 1

    async def load() -> str:
        loads.append(1)
        started.set()
        await asyncio.sleep(30)
        return "never"

    task = asyncio.create_task(
        load_reporting_result_once_stable(
            read_epoch=read_epoch, load=load, operation="unit"
        )
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(loads) == 1


@pytest.mark.asyncio
async def test_instability_retry_does_not_reuse_first_attempt_tasks() -> None:
    """Every period task of a discarded attempt is settled before the retry."""
    epochs = iter([1, 2, 2, 2])
    attempt_period_tasks: list[list[asyncio.Task[Any]]] = []
    attempt_total_reads: list[int] = []

    async def read_epoch() -> int:
        return next(epochs)

    class _Repo:
        async def fetch_report_rows(self, **kwargs: Any) -> list[Any]:
            task = asyncio.current_task()
            assert task is not None
            if kwargs.get("period"):
                if len(attempt_period_tasks) < len(attempt_total_reads):
                    attempt_period_tasks.append([])
                attempt_period_tasks[-1].append(task)
                await asyncio.sleep(0.01)
                return []
            attempt_total_reads.append(len(attempt_total_reads) + 1)
            return []

    service = ExportsService(_Repo())  # type: ignore[arg-type]
    service.repo.fetch_sales_generation_epoch = read_epoch  # type: ignore[attr-defined]
    plan = service._report_plan(export_request("2026-05"))
    loaded = await service._load_report_once_stable(
        plan, row_limit=100, preview_limit=None
    )

    assert len(attempt_total_reads) == 2
    assert len(attempt_period_tasks) == 2
    first, second = attempt_period_tasks
    assert len(first) == 2
    assert len(second) == 2
    assert all(task.done() for task in first)
    assert all(task.done() for task in second)
    assert set(first).isdisjoint(second)
    assert loaded.rows == {}


@pytest.mark.asyncio
async def test_period_loader_cancellation_settles_every_sibling_task() -> None:
    started_month = asyncio.Event()
    started_day = asyncio.Event()
    cancelled: list[str] = []
    observed: list[asyncio.Task[Any]] = []

    class _Repo:
        async def fetch_sales_generation_epoch(self) -> int:
            return 1

        async def fetch_report_rows(self, **kwargs: Any) -> list[Any]:
            name = str(kwargs.get("period"))
            if name == "month":
                started_month.set()
            elif name == "day":
                started_day.set()
            else:
                return []
            task = asyncio.current_task()
            assert task is not None
            observed.append(task)
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                cancelled.append(name)
                raise
            return []

    async def run() -> None:
        service = ExportsService(_Repo())  # type: ignore[arg-type]
        plan = service._report_plan(export_request("2026-05"))
        await service._load_report_once_stable(plan, row_limit=100, preview_limit=None)

    task = asyncio.create_task(run())
    await started_month.wait()
    await started_day.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(observed) == 2
    for sibling in observed:
        assert sibling.done()
    assert sorted(cancelled) == ["day", "month"]


@requires_postgres
@pytest.mark.asyncio
async def test_fenced_export_never_opens_a_db_transaction() -> None:
    url = database_url()
    month = next_month()
    await seed_generation_a(url, month, forecast_run=False)
    pool = await _pool(url)
    try:
        service = ExportsService(
            ExportsRepository(ObservedPool(pool, forbid_transaction=True))
        )
        result = await service.build_report(export_request(month))
        total, monthly, daily = export_values(result)
        assert total == monthly == daily == Decimal(GENERATION_A["value"])
    finally:
        await pool.close()


@requires_postgres
@pytest.mark.asyncio
async def test_fenced_export_returns_every_pooled_connection() -> None:
    url = database_url()
    month = next_month()
    await seed_generation_a(url, month, forecast_run=False)
    pool = await _pool(url)
    try:
        hook = _Hook(
            _is_export_total_read,
            lambda: promote_generation(url, month, GENERATION_B),
        )
        service = ExportsService(ExportsRepository(ObservedPool(pool, hook)))
        await service.build_report(export_request(month))

        assert pool.get_size() == pool.get_idle_size()
    finally:
        await pool.close()


# ---------------------------------------------------------------------------
# Deliberate non-changes
# ---------------------------------------------------------------------------


@requires_postgres
@pytest.mark.asyncio
async def test_rolling_12_reads_all_sales_data_in_one_statement() -> None:
    """Rolling-12 has no comparable multi-statement boundary, so it stays unfenced."""
    url = database_url()
    month = next_month()
    await seed_generation_a(url, month, forecast_run=True)
    await seed_rolling_run(url, month)
    pool = await _pool(url)
    try:
        observed = ObservedPool(pool)
        service = AiForecastService(AiForecastRepository(observed))
        response = await service.get_rolling_12(**forecast_request(month))

        assert response is not None
        assert [point.forecast_month for point in response.months]
        sales_statements = [
            sql for sql in observed.statements if "reporting_agent_month" in sql
        ]
        assert len(sales_statements) == 1
        assert "SELECT public.current_sales_generation_epoch()" not in observed.statements
    finally:
        await pool.close()
