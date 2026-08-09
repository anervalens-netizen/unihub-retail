from __future__ import annotations

import asyncio
from io import BytesIO
import json
import os
from pathlib import Path
import sys
from typing import Any

from arq.jobs import JobStatus
import pandas as pd

from db.connection import close_db_pool, get_pool
from services.importer import SALES_COLUMNS, reserve_snapshot
from services.jobs import close_arq_pool, enqueue_sales_import


TEST_MONTH = "2099-11"
TEST_DATE = "01.11.2099"
STALE_MONTH = "2099-12"
STALE_DATE = "01.12.2099"


def workbook(marker: str, business_date: str = TEST_DATE) -> bytes:
    rows = [
        {
            "Data": business_date,
            "SiteCode": "E2E-OVERLAP",
            "ItemCode": f"ITEM-{marker}",
            "ItemName": f"Produs {marker}",
            "Cantitate": 1,
            "Brand": "E2E",
            "Pret": 10,
            "Valoare": 10,
            "Locatie": "Magazin E2E",
            "Firma": "Mobiup",
            "ASM": "Manager E2E",
            "Regional": "Regional E2E",
            "Nr": f"BON-{marker}-{index}",
            "Categorie": "Accesorii",
            "SubCategorie": "Test",
            "Agent": "Agent E2E",
        }
        for index in range(50)
    ]
    output = BytesIO()
    pd.DataFrame(rows, columns=SALES_COLUMNS).to_excel(output, index=False)
    return output.getvalue()


async def start_worker(log_path: Path) -> tuple[asyncio.subprocess.Process, Any]:
    log_file = log_path.open("wb")
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "worker.py",
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "RETAIL_WORKER_ROLE": "imports"},
        stdout=log_file,
        stderr=asyncio.subprocess.STDOUT,
    )
    return process, log_file


async def stop_worker(process: asyncio.subprocess.Process, log_file: Any) -> None:
    if process.returncode is None:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=30)
        except TimeoutError:
            process.kill()
            await process.wait()
    log_file.close()


async def wait_for_jobs(jobs: list[Any], *, timeout: float = 90) -> list[Any]:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        statuses = await asyncio.gather(*(job.status() for job in jobs))
        if all(status == JobStatus.complete for status in statuses):
            return await asyncio.gather(*(job.result_info() for job in jobs))
        await asyncio.sleep(0.2)
    raise RuntimeError("timed out waiting for import worker results")


async def install_overlap_hold_trigger(pool: Any) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE OR REPLACE FUNCTION real_e2e_hold_import_reservation()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.import_month = '2099-11' THEN
                    PERFORM pg_sleep(2);
                END IF;
                RETURN NEW;
            END;
            $$;
            DROP TRIGGER IF EXISTS real_e2e_hold_import_reservation
                ON import_snapshots;
            CREATE TRIGGER real_e2e_hold_import_reservation
                BEFORE INSERT ON import_snapshots
                FOR EACH ROW EXECUTE FUNCTION real_e2e_hold_import_reservation();
            """
        )


def write_evidence(output_path: Path) -> None:
    output_path.write_text(
        json.dumps(
            {
                "status": "passed",
                "worker_role": "imports",
                "queue": "arq:retail:imports",
                "worker_processes": 2,
                "worker_processed_imports": 3,
                "overlapping_imports": 2,
                "accepted": 1,
                "lease_conflicts": 1,
                "stale_lease_audited_on_worker_restart": True,
                "replacement_processed_by_worker": True,
                "database": "isolated",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


async def main(output_path: Path) -> None:
    runtime_dir = output_path.parent / "real-e2e-runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    pool = await get_pool()
    workers: list[tuple[asyncio.subprocess.Process, Any]] = []
    try:
        await install_overlap_hold_trigger(pool)

        workers = [
            await start_worker(runtime_dir / "import-overlap-worker-a.log"),
            await start_worker(runtime_dir / "import-overlap-worker-b.log"),
        ]
        await asyncio.sleep(2)
        jobs = await asyncio.gather(
            enqueue_sales_import(
                workbook("A"),
                "overlap-a.xlsx",
                cutoff_date="2099-11-01",
                requested_by_sub="real-e2e",
            ),
            enqueue_sales_import(
                workbook("B"),
                "overlap-b.xlsx",
                cutoff_date="2099-11-01",
                requested_by_sub="real-e2e",
            ),
        )
        results = await wait_for_jobs(list(jobs))
        successes = [result for result in results if result is not None and result.success]
        failures = [result for result in results if result is not None and not result.success]
        if len(successes) != 1 or len(failures) != 1:
            raise RuntimeError("real worker overlap did not produce one success and one lease conflict")
        if "import in curs" not in str(failures[0].result):
            raise RuntimeError(f"unexpected overlap failure: {failures[0].result}")

        for worker_process, log_file in workers:
            await stop_worker(worker_process, log_file)
        workers = []

        # Model a process death after reservation but before validation. The
        # restarted real import worker must perform the stale-lease audit.
        async with pool.acquire() as conn:
            stale_snapshot_id = await reserve_snapshot(
                conn,
                STALE_MONTH,
                "interrupted-before-validation.xlsx",
                rows_in_file=1,
            )
            await conn.execute(
                """
                UPDATE import_snapshots
                SET heartbeat_at = now() - interval '2 hours',
                    lease_until = now() - interval '1 second'
                WHERE id = $1
                """,
                stale_snapshot_id,
            )
        restarted = await start_worker(runtime_dir / "import-overlap-worker-restarted.log")
        workers.append(restarted)
        stale_state = None
        restart_deadline = asyncio.get_running_loop().time() + 30
        while asyncio.get_running_loop().time() < restart_deadline:
            if restarted[0].returncode is not None:
                raise RuntimeError("restarted import worker exited during reconciliation")
            async with pool.acquire() as conn:
                stale_state = await conn.fetchrow(
                    "SELECT status, finished_at IS NOT NULL AS finished FROM import_snapshots WHERE id = $1",
                    stale_snapshot_id,
                )
            if stale_state is not None and stale_state["status"] == "failed":
                break
            await asyncio.sleep(0.2)
        if stale_state is None or stale_state["status"] != "failed" or not stale_state["finished"]:
            raise RuntimeError("import worker restart did not audit the stale lease as failed")

        replacement = await enqueue_sales_import(
            workbook("REPLACEMENT", STALE_DATE),
            "replacement.xlsx",
            cutoff_date="2099-12-01",
            requested_by_sub="real-e2e",
        )
        replacement_result = (await wait_for_jobs([replacement]))[0]
        if replacement_result is None or not replacement_result.success:
            raise RuntimeError(f"replacement import failed: {replacement_result}")

        async with pool.acquire() as conn:
            states = await conn.fetch(
                """
                SELECT status, finished_at IS NOT NULL AS finished
                FROM import_snapshots WHERE import_month = $1 ORDER BY id
                """,
                STALE_MONTH,
            )
        state_summary = [
            {"status": str(row["status"]), "finished": bool(row["finished"])}
            for row in states
        ]
        if state_summary != [
            {"status": "failed", "finished": True},
            {"status": "processing", "finished": False},
        ]:
            raise RuntimeError(f"unexpected worker-produced import states: {state_summary}")

        write_evidence(output_path)
    finally:
        for worker_process, log_file in workers:
            await stop_worker(worker_process, log_file)
        async with pool.acquire() as conn:
            await conn.execute(
                "DROP TRIGGER IF EXISTS real_e2e_hold_import_reservation ON import_snapshots"
            )
            await conn.execute("DROP FUNCTION IF EXISTS real_e2e_hold_import_reservation()")
        await close_arq_pool()
        await close_db_pool()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: run_import_overlap_gate.py OUTPUT_JSON")
    asyncio.run(main(Path(sys.argv[1])))
