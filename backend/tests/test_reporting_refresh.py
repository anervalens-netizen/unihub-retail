from __future__ import annotations

from typing import Any

import pytest
from openpyxl import Workbook

import services.reporting_refresh as reporting_refresh


class FakeTransaction:
    def __init__(self, conn: "FakeConn") -> None:
        self.conn = conn

    async def __aenter__(self) -> None:
        self.conn.events.append(("transaction_enter", None, ()))

    async def __aexit__(self, *_args: Any) -> None:
        self.conn.events.append(("transaction_exit", None, ()))


class FakeConn:
    def __init__(self) -> None:
        self.events: list[tuple[str, str | None, tuple[Any, ...]]] = []
        self.fetch_rows: list[dict[str, Any]] = []

    async def execute(self, sql: str, *args: Any) -> None:
        self.events.append(("execute", " ".join(sql.split()), args))

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        self.events.append(("fetch", " ".join(sql.split()), args))
        return self.fetch_rows

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self)


def executed_sql(conn: FakeConn) -> list[str]:
    return [sql or "" for kind, sql, _args in conn.events if kind == "execute"]


def test_premium_glass_screen_targets_exclude_samsung_s26_plus() -> None:
    sql = reporting_refresh._PREMIUM_GLASS_INSERT_SQL

    assert "('samsung_s26_plus'" not in sql
    assert "SAMSUNG GALAXY S26 PLUS|S26 PLUS" not in sql
    assert "('samsung_s26', 'Samsung S26'" in sql
    assert "('samsung_s26_ultra', 'Samsung S26 Ultra'" in sql


@pytest.mark.asyncio
async def test_rebuild_reporting_month_applies_destructive_steps_and_scope_guards() -> None:
    conn = FakeConn()

    await reporting_refresh.rebuild_reporting_month(conn, "2026-06")  # type: ignore[arg-type]

    sql = executed_sql(conn)
    assert sql[0] == "DROP TABLE IF EXISTS tmp_reporting_receipts"
    assert sql[-1] == "DROP TABLE IF EXISTS tmp_reporting_receipts"

    for table in [
        "reporting_category_month",
        "reporting_focus_item_month",
        "reporting_agent_month",
        "reporting_item_day",
        "reporting_item_month",
        "reporting_agent_day",
    ]:
        assert any(f"DELETE FROM {table} WHERE import_month = $1" in statement for statement in sql)
        assert any(f"ANALYZE {table}" in statement for statement in sql)

    insert_statements = [
        statement
        for statement in sql
        if "FROM sales_transactions st" in statement
        and "premium_glass_item_models" not in statement
    ]
    assert insert_statements
    assert all("NOT st.is_cartela" in statement for statement in insert_statements)
    assert all("s.locatie NOT ILIKE 'TR %'" in statement for statement in insert_statements)
    assert any("TRUNCATE premium_glass_item_models" in statement for statement in sql)

    month_args = [
        args
        for kind, _sql, args in conn.events
        if kind == "execute" and args == ("2026-06",)
    ]
    assert len(month_args) >= 7


@pytest.mark.asyncio
async def test_refresh_premium_glass_indicators_loads_camera_premium_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = FakeConn()
    monkeypatch.setattr(
        reporting_refresh,
        "_load_premium_camera_rows",
        lambda: (
            ["WS81519", "WS81519"],
            ["Camera S26/S26 Plus", "Camera S26/S26 Plus"],
            [True, True],
            ["samsung_s26", "samsung_s26_plus"],
            ["Samsung S26", "Samsung S26 Plus"],
        ),
    )

    await reporting_refresh.refresh_premium_glass_indicators(conn)  # type: ignore[arg-type]

    assert conn.events[0][1] == "TRUNCATE premium_glass_item_models"
    assert conn.events[1][2] == (
        ["WS81519", "WS81519"],
        ["Camera S26/S26 Plus", "Camera S26/S26 Plus"],
        [True, True],
        ["samsung_s26", "samsung_s26_plus"],
        ["Samsung S26", "Samsung S26 Plus"],
    )
    sql = conn.events[1][1] or ""
    assert "camera_products" in sql
    assert "is_premium_glass" in sql
    assert conn.events[2][1] == "ANALYZE premium_glass_item_models"


def test_load_premium_camera_rows_reads_workbook(tmp_path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Folii Camera"
    sheet.append(["Cod", "ItemName", "Premium"])
    sheet.append(["WS81519", "SAMSUNG GALAXY S26 5G/S26 PLUS 5G", "Da"])
    sheet.append(["", "SAMSUNG GALAXY S26 5G", "Da"])
    sheet.append(["WS00000", "", "Da"])
    sheet.append(["WS00001", "Husa simpla", "Nu"])
    source = tmp_path / "camera.xlsx"
    workbook.save(source)

    rows = reporting_refresh._load_premium_camera_rows(source)

    assert rows == (
        ["WS81519", "WS81519"],
        ["SAMSUNG GALAXY S26 5G/S26 PLUS 5G", "SAMSUNG GALAXY S26 5G/S26 PLUS 5G"],
        [True, True],
        ["samsung_s26", "samsung_s26_plus"],
        ["Samsung S26", "Samsung S26 Plus"],
    )


def test_load_premium_camera_rows_handles_missing_or_invalid_workbook(tmp_path) -> None:
    assert reporting_refresh._load_premium_camera_rows(tmp_path / "missing.xlsx") == (
        [],
        [],
        [],
        [],
        [],
    )

    workbook = Workbook()
    workbook.active.append(["Cod", "Premium"])
    source = tmp_path / "invalid.xlsx"
    workbook.save(source)

    assert reporting_refresh._load_premium_camera_rows(source) == ([], [], [], [], [])


@pytest.mark.asyncio
async def test_rebuild_agent_lifecycle_reporting_refreshes_lifecycle_tables() -> None:
    conn = FakeConn()

    await reporting_refresh.rebuild_agent_lifecycle_reporting(conn)  # type: ignore[arg-type]

    sql = executed_sql(conn)
    assert sql[0] == "DELETE FROM reporting_agent_lifecycle_month"
    assert sql[1] == "DELETE FROM reporting_agent_profile"
    assert "INSERT INTO reporting_agent_lifecycle_month" in sql[2]
    assert "COUNT(DISTINCT firma)::INT AS active_firma_count" in sql[2]
    assert "gap_since_prev_active_months" in sql[2]
    assert "INSERT INTO reporting_agent_profile" in sql[3]
    assert "COUNT(DISTINCT firma)::INT AS distinct_firma_count" in sql[3]
    assert "current_status" in sql[3]
    assert sql[-2] == "ANALYZE reporting_agent_lifecycle_month"
    assert sql[-1] == "ANALYZE reporting_agent_profile"


@pytest.mark.asyncio
async def test_list_completed_import_months_uses_completed_snapshots_ordered() -> None:
    conn = FakeConn()
    conn.fetch_rows = [{"import_month": "2026-05"}, {"import_month": "2026-06"}]

    months = await reporting_refresh.list_completed_import_months(conn)  # type: ignore[arg-type]

    assert months == ["2026-05", "2026-06"]
    fetch_sql = conn.events[0][1] or ""
    assert "FROM import_snapshots" in fetch_sql
    assert "WHERE status = 'completed'" in fetch_sql
    assert "ORDER BY import_month ASC" in fetch_sql


@pytest.mark.asyncio
async def test_rebuild_reporting_all_wraps_each_month_and_refreshes_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = FakeConn()
    calls: list[tuple[str, str | None]] = []

    async def rebuild_month(_conn: FakeConn, month: str) -> None:
        calls.append(("month", month))

    async def rebuild_lifecycle(_conn: FakeConn) -> None:
        calls.append(("lifecycle", None))

    monkeypatch.setattr(reporting_refresh, "rebuild_reporting_month", rebuild_month)
    monkeypatch.setattr(reporting_refresh, "rebuild_agent_lifecycle_reporting", rebuild_lifecycle)

    result = await reporting_refresh.rebuild_reporting_all(conn, ["2026-05", "2026-06"])  # type: ignore[arg-type]

    assert result == ["2026-05", "2026-06"]
    assert calls == [("month", "2026-05"), ("month", "2026-06"), ("lifecycle", None)]
    assert [event[0] for event in conn.events] == [
        "transaction_enter",
        "transaction_exit",
        "transaction_enter",
        "transaction_exit",
        "transaction_enter",
        "transaction_exit",
    ]
