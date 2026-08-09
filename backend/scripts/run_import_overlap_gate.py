from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys

from db.connection import close_db_pool, get_pool
from services.importer import (
    ImportAlreadyRunningError,
    reconcile_interrupted_imports,
    reserve_snapshot,
)


TEST_MONTH = "2099-11"


async def main(output_path: Path) -> None:
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM import_snapshots WHERE import_month = $1",
                TEST_MONTH,
            )

        async def attempt(filename: str) -> int | ImportAlreadyRunningError:
            try:
                async with pool.acquire() as conn:
                    return await reserve_snapshot(
                        conn,
                        TEST_MONTH,
                        filename,
                        rows_in_file=1,
                    )
            except ImportAlreadyRunningError as exc:
                return exc

        attempts = await asyncio.gather(
            attempt("overlap-a.xlsx"),
            attempt("overlap-b.xlsx"),
        )
        accepted = [value for value in attempts if isinstance(value, int)]
        rejected = [
            value for value in attempts if isinstance(value, ImportAlreadyRunningError)
        ]
        if len(accepted) != 1 or len(rejected) != 1:
            raise RuntimeError("monthly import lease did not fence the overlap")

        first_snapshot_id = accepted[0]
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE import_snapshots
                SET heartbeat_at = now() - interval '2 hours',
                    lease_until = now() - interval '1 second'
                WHERE id = $1
                """,
                first_snapshot_id,
            )
        reconciled = await reconcile_interrupted_imports(pool)
        if first_snapshot_id not in reconciled:
            raise RuntimeError("stale monthly import lease was not audited as failed")

        async with pool.acquire() as conn:
            replacement_id = await reserve_snapshot(
                conn,
                TEST_MONTH,
                "replacement.xlsx",
                rows_in_file=1,
            )
            states = await conn.fetch(
                """
                SELECT id, status, finished_at IS NOT NULL AS finished
                FROM import_snapshots
                WHERE import_month = $1
                ORDER BY id
                """,
                TEST_MONTH,
            )
        state_summary = [
            {"status": str(row["status"]), "finished": bool(row["finished"])}
            for row in states
        ]
        if state_summary != [
            {"status": "failed", "finished": True},
            {"status": "processing", "finished": False},
        ]:
            raise RuntimeError(f"unexpected stale-lease audit state: {state_summary}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {
                    "status": "passed",
                    "worker_role": "imports",
                    "queue": "arq:retail:imports",
                    "overlapping_attempts": 2,
                    "accepted": 1,
                    "lease_conflicts": 1,
                    "stale_lease_audited_failed": True,
                    "replacement_reserved": replacement_id > first_snapshot_id,
                    "database": "isolated",
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    finally:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM import_snapshots WHERE import_month = $1",
                TEST_MONTH,
            )
        await close_db_pool()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: run_import_overlap_gate.py OUTPUT_JSON")
    asyncio.run(main(Path(sys.argv[1])))
