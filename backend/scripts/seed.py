from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from bootstrap import ensure_tl_users_and_assignments
from db.connection import close_db_pool, get_pool, init_db_pool
from db.migration_runner import verify_migrations_current
from services.importer import (
    detect_month,
    import_sales_dataframe,
    load_sales_dataframe,
    load_targets_dataframe,
    upsert_store_targets,
)
from services.product_lists import sync_focus_products
from services.reporting_refresh import rebuild_reporting_all


def get_data_dir() -> Path:
    return ROOT_DIR.parent / "data"


def format_int(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def resolve_input_files(input_path: str | None) -> tuple[list[Path], list[Path], list[Path]]:
    data_dir = get_data_dir()
    if input_path:
        requested = Path(input_path)
        if not requested.is_absolute():
            requested = (ROOT_DIR.parent / requested).resolve()
        if not requested.exists():
            raise FileNotFoundError(f"Fisierul nu exista: {requested}")
        if "target" in requested.name.lower():
            return [], [requested], []
        if "focus" in requested.name.lower():
            return [], [], [requested]
        return [requested], [], []

    files = sorted(data_dir.glob("*.xlsx")) + sorted(data_dir.glob("*.xls"))
    sales_files = [
        path
        for path in files
        if "target" not in path.name.lower() and "focus" not in path.name.lower()
    ]
    target_files = [path for path in files if "target" in path.name.lower()]
    focus_files = [path for path in files if "focus" in path.name.lower()]
    return sales_files, target_files, focus_files


async def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk seed pentru date UniHub")
    parser.add_argument(
        "input_path",
        nargs="?",
        help="Fisier specific de importat, relativ la repo sau absolut",
    )
    args = parser.parse_args()

    await init_db_pool()
    await verify_migrations_current(await get_pool())
    pool = await get_pool()

    sales_files, target_files, focus_files = resolve_input_files(args.input_path)

    month_pairs = []
    for path in sales_files:
        df = load_sales_dataframe(path)
        month_pairs.append((detect_month(df), path, df))
    month_pairs.sort(key=lambda item: item[0])

    total_rows = 0
    processed_months: list[str] = []
    async with pool.acquire() as conn:
        for month, path, df in month_pairs:
            result = await import_sales_dataframe(conn, df, filename=path.name)
            total_rows += result.rows_imported
            processed_months.append(result.import_month)
            print(
                f"* {result.import_month} | {format_int(result.rows_imported)} randuri | "
                f"{result.agent_count} agenti | {result.store_count} magazine"
            )

        for target_file in target_files:
            targets = load_targets_dataframe(target_file)
            inserted = await upsert_store_targets(conn, targets, target_file.name)
            print(f"* targete | {target_file.name} | {format_int(inserted)} inregistrari")

        for focus_file in focus_files:
            synced = await sync_focus_products(conn, focus_file)
            print(f"* focus products | {focus_file.name} | {format_int(synced)} coduri")
        if focus_files:
            await rebuild_reporting_all(conn)

        await ensure_tl_users_and_assignments(conn)

    print(
        f"Import finalizat | luni: {len(processed_months)} | "
        f"randuri: {format_int(total_rows)} | luni procesate: {', '.join(processed_months)}"
    )
    await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
